"""The deterministic scan pipeline and its CLI (Phase 1).

Runs the three legal trajectories from agent/system_prompt.md as plain code:
cache hit, columnar reject, or full scan (Presidio path only — the GenAI leg
and the Managed Agents session arrive in Phases 2–3, wrapping these same
functions unchanged).

Usage:
    PII_ENGINE=presidio python -m pipeline.scan <file> --user <login>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from pipeline import TAXONOMY_VERSION
from pipeline.checksum import compute_pipeline_version, sha256_file
from pipeline.chunking import chunk_text
from pipeline.compliance import map_compliance_impact
from pipeline.engine import resolve_pii_engine, uses_genai, uses_presidio
from pipeline.extract import ExtractionError, extract_text
from pipeline.normalize import normalize_findings
from pipeline.schemas import DocumentMeta, DocumentResult, RunInfo
from pipeline.storage import db, s3
from pipeline.structure import classify_structure, is_in_scope


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _base_meta(path: Path, structural_class: str) -> dict:
    return {
        "source_path": str(path),
        "file_name": path.name,
        "file_type": path.suffix.lstrip(".").lower() or "unknown",
        "size_bytes": path.stat().st_size,
        "structural_class": structural_class,
    }


def scan_document(
    path: str | Path,
    user_login: str,
    engine: str,
    conn=None,
    analyzer=None,
) -> DocumentResult:
    """Run one document through the deterministic pipeline.

    `conn` (DB) and `analyzer` (Presidio) are injectable for tests; when None,
    the real ones are constructed. GenAI engines fail loudly until Phase 3.
    """
    if uses_genai(engine):
        raise RuntimeError(f"PII_ENGINE={engine}: the GenAI path lands in Phase 3")

    p = Path(path)
    started = _now_iso()
    t0 = time.monotonic()
    checksum = sha256_file(p)
    pipeline_version = compute_pipeline_version(engine, [], "", TAXONOMY_VERSION)
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    own_conn = conn is None
    conn = conn or db.connect()

    try:
        # Trajectory 1 — cache hit
        cached = db.cache_lookup(conn, checksum, pipeline_version)
        if cached is not None:
            return cached

        sample = p.read_text(encoding="utf-8", errors="ignore")[:4096] if p.suffix.lower() in {".txt", ".md", ".text"} else None
        structural_class = classify_structure(p, sample_text=sample)

        # Trajectory 2 — columnar reject
        if not is_in_scope(structural_class):
            result = _finish(
                conn, p, checksum, user_login, engine, pipeline_version, scan_id,
                started, t0,
                DocumentMeta(**_base_meta(p, structural_class),
                             processing_status="skipped_out_of_scope",
                             reason="structured_columnar"),
                findings=[],
            )
            return result

        # Trajectory 3 — full scan (deterministic leg)
        try:
            extraction = extract_text(p)
        except ExtractionError as exc:
            return _finish(
                conn, p, checksum, user_login, engine, pipeline_version, scan_id,
                started, t0,
                DocumentMeta(**_base_meta(p, structural_class),
                             processing_status="failed", reason=exc.reason),
                findings=[],
            )

        chunks = chunk_text(extraction.text)
        raw = []
        if uses_presidio(engine):
            from pipeline.presidio_scan import get_analyzer, scan_with

            raw = scan_with(analyzer or get_analyzer(), extraction.text, chunks)

        meta = DocumentMeta(
            **_base_meta(p, structural_class),
            page_count=extraction.page_count,
            processing_status="processed",
            ocr_enabled=extraction.ocr_enabled,
            extraction_method=extraction.method,
            chunk_count=len(chunks),
        )
        return _finish(
            conn, p, checksum, user_login, engine, pipeline_version, scan_id,
            started, t0, meta, findings=normalize_findings(raw),
        )
    finally:
        if own_conn:
            conn.close()


def _finish(conn, p, checksum, user_login, engine, pipeline_version, scan_id,
            started, t0, meta: DocumentMeta, findings) -> DocumentResult:
    """Assemble, persist (DB + S3 mirror), and return the result."""
    result = DocumentResult(
        checksum=checksum,
        user_login=user_login,
        document=meta,
        findings=findings,
        compliance_impact=map_compliance_impact([f.canonical_type for f in findings]),
        run=RunInfo(
            scan_id=scan_id, pipeline_version=pipeline_version, engine=engine,
            started_at=started, ended_at=_now_iso(),
        ),
    )
    today = date.today()
    upload = s3.put_file(p, s3.upload_key(user_login, today, checksum, p.name))
    s3.put_bytes(result.model_dump_json(indent=2).encode(),
                 s3.result_key(user_login, today, checksum))
    db.upsert_document(conn, result, upload.uploaded[0] if upload.uploaded else None)
    db.insert_scan(conn, result, latency_ms=int((time.monotonic() - t0) * 1000))
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: scan one file, print a summary, exit non-zero on failure."""
    parser = argparse.ArgumentParser(description="Deterministic PII scan (Phase 1)")
    parser.add_argument("file")
    parser.add_argument("--user", required=True, help="user_login for partitioning")
    parser.add_argument("--json", action="store_true", help="print full result JSON")
    args = parser.parse_args(argv)

    engine = resolve_pii_engine()
    result = scan_document(args.file, user_login=args.user, engine=engine)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        counts = {f.canonical_type: f.occurrences for f in result.findings}
        print(json.dumps({
            "scan_id": result.run.scan_id,
            "status": result.document.processing_status,
            "reason": result.document.reason,
            "findings": counts,
            "jurisdictions": result.compliance_impact.impacted_jurisdictions,
        }, indent=2))
    return 0 if result.document.processing_status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
