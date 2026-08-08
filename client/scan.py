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
from pipeline.schemas import DocumentResult
from pipeline.storage import db
from client.session import run_session

APPLIED = Path(__file__).resolve().parent.parent / "agent" / "applied.json"


def _load_result(conn, scan_id: str) -> DocumentResult | None:
    """Fetch a persisted result regardless of status (cache_lookup is
    processed-only by design — judging needs reject/failed rows too, to skip
    them explicitly rather than silently finding nothing)."""
    row = conn.execute("SELECT result_json FROM scans WHERE scan_id = ?", [scan_id]).fetchone()
    return DocumentResult.model_validate_json(row[0]) if row and row[0] else None


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
        # Fixed 2026-08-08 (real gap against PRD §10.3): a cache hit used to
        # leave zero trace anywhere — no session, no forwarder call, no new
        # DB row. Now it gets a durable record and a minimal trace, so
        # "cache hit rate" is actually computable, without creating a
        # session or spending a token.
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        db.record_cache_hit(conn, request_id, cached.run.scan_id, checksum, args.user)
        try:
            from client.forwarder import forward_cache_hit
            forward_cache_hit(request_id, cached.run.scan_id, checksum, args.user,
                              datetime.now(timezone.utc))
        except Exception as exc:  # noqa: BLE001 — telemetry never fails a scan
            print(f"forwarder warning: {exc}", file=sys.stderr)
        print(json.dumps({"cache_hit": True, "request_id": request_id,
                          "scan_id": cached.run.scan_id,
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
    forward_summary = {"span_count": 0, "root_span_id": None, "root_trace_id": None}
    try:
        from client.forwarder import forward_session
        forward_summary = forward_session(outcome.events, scan_meta={
            "session_id": outcome.session_id, "user_login": args.user,
            "checksum": checksum, "cache_hit": False,
        })
    except Exception as exc:  # noqa: BLE001 — telemetry never fails a scan
        print(f"forwarder warning: {exc}", file=sys.stderr)

    persisted = _load_result(conn, manifest["scan_id"])
    if persisted is not None:
        db.record_span(conn, manifest["scan_id"],
                       forward_summary["root_span_id"], forward_summary["root_trace_id"])

    # Phase 5: judge + push (env-gated inside; degrades to one warning; the
    # document is still on disk here, which is why this runs now rather than
    # as a deferred batch job — see ADR 0002).
    judge_summary = {"judged": False, "pushed": False}
    if persisted is not None:
        try:
            from evals.judge.push import judge_and_push
            judge_summary = judge_and_push(persisted, args.file,
                                           forward_summary["root_span_id"], conn)
        except Exception as exc:  # noqa: BLE001 — never fails a scan
            print(f"judge_push warning: {exc}", file=sys.stderr)

    print(json.dumps({
        "cache_hit": False,
        "scan_id": manifest["scan_id"],
        "session_id": outcome.session_id,
        "terminal": outcome.terminal,
        "persisted_status": persisted.document.processing_status if persisted else None,
        "findings": {f.canonical_type: f.occurrences for f in persisted.findings} if persisted else None,
        "eval": judge_summary,
    }, indent=2))
    return 0 if persisted else 1


if __name__ == "__main__":
    sys.exit(main())
