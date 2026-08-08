"""Scan CLI (Phase 2): one document → one Managed Agents session → one result.

The cache check runs CLIENT-SIDE before any session exists — a cache hit
creates no session at all (PRD flow step 4). Everything else is the agent's
job; this process only uploads, kicks off, and answers custom tool calls.

Usage:
    PII_ENGINE=presidio python -m client.scan <file> --user <login>
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

from pipeline import TAXONOMY_VERSION
from pipeline.checksum import compute_pipeline_version, sha256_file
from pipeline.engine import resolve_pii_engine, uses_genai
from pipeline.storage import db
from client.session import run_session

APPLIED = Path(__file__).resolve().parent.parent / "agent" / "applied.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a document via the Managed Agent")
    parser.add_argument("file")
    parser.add_argument("--user", required=True)
    parser.add_argument("--events-out", help="write the session event log (JSON) here")
    args = parser.parse_args(argv)

    engine = resolve_pii_engine()
    if uses_genai(engine):
        raise SystemExit(f"PII_ENGINE={engine}: the GenAI path lands in Phase 3")

    ids = json.loads(APPLIED.read_text())
    checksum = sha256_file(args.file)
    pipeline_version = compute_pipeline_version(engine, [], "", TAXONOMY_VERSION)

    conn = db.connect()
    cached = db.cache_lookup(conn, checksum, pipeline_version)
    if cached is not None:
        print(json.dumps({"cache_hit": True, "scan_id": cached.run.scan_id,
                          "status": cached.document.processing_status}, indent=2))
        return 0

    manifest = {
        "scan_id": f"scan_{uuid.uuid4().hex[:12]}",
        "checksum": checksum,
        "user_login": args.user,
        "engine": engine,
        "models": [],
        "pipeline_version": pipeline_version,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "check_cache": False,  # client already checked; trajectory 1 not needed
    }
    outcome = run_session(
        Anthropic(),
        agent_id=ids["orchestrator_id"],
        agent_version=int(ids["orchestrator_version"]),
        environment_id=ids["environment_id"],
        document_path=args.file,
        manifest=manifest,
        conn=conn,
    )

    if args.events_out:
        Path(args.events_out).write_text(json.dumps(
            [e.model_dump(mode="json") for e in outcome.events], indent=2, default=str))

    # Phase 4: forward the trace (env-gated inside; degrades to one warning).
    try:
        from client.forwarder import forward_session
        forward_session(outcome.events, scan_meta={
            "session_id": outcome.session_id, "user_login": args.user,
            "checksum": checksum, "cache_hit": False,
        })
    except Exception as exc:  # noqa: BLE001 — telemetry never fails a scan
        print(f"forwarder warning: {exc}", file=sys.stderr)

    persisted = db.cache_lookup(conn, checksum, pipeline_version)
    row = conn.execute(
        "SELECT status FROM scans WHERE scan_id = ?", [manifest["scan_id"]]
    ).fetchone()
    print(json.dumps({
        "cache_hit": False,
        "scan_id": manifest["scan_id"],
        "session_id": outcome.session_id,
        "terminal": outcome.terminal,
        "persisted_status": row[0] if row else None,
        "findings": {f.canonical_type: f.occurrences for f in persisted.findings} if persisted else None,
    }, indent=2))
    return 0 if row else 1


if __name__ == "__main__":
    sys.exit(main())
