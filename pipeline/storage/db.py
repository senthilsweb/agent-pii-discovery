"""The database seam — the only module that imports a DB driver.

DuckDB in v1; the DDL is ANSI-portable (TEXT/BIGINT/DOUBLE/TIMESTAMP,
app-generated ids, JSON as TEXT) so production can swap in Postgres/MySQL by
replacing `connect()` and the `?` placeholder style, with no schema change.
Nothing outside this module may import duckdb.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.schemas import DocumentResult

_DDL = [
    """CREATE TABLE IF NOT EXISTS documents (
        checksum        TEXT PRIMARY KEY,
        user_login      TEXT NOT NULL,
        file_name       TEXT NOT NULL,
        mime_type       TEXT,
        size_bytes      BIGINT,
        page_count      INTEGER,
        s3_key          TEXT,
        first_seen_at   TIMESTAMP NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS scans (
        scan_id          TEXT PRIMARY KEY,
        checksum         TEXT NOT NULL,
        pipeline_version TEXT NOT NULL,
        engine           TEXT NOT NULL,
        models           TEXT,
        session_id       TEXT,
        status           TEXT NOT NULL,
        result_json      TEXT,
        latency_ms       BIGINT,
        cost_usd         DOUBLE,
        started_at       TIMESTAMP NOT NULL,
        ended_at         TIMESTAMP,
        root_span_id     TEXT,
        root_trace_id    TEXT,
        judged_at        TIMESTAMP
    )""",
    # Migration for DBs created before the eval-push columns existed —
    # CREATE TABLE IF NOT EXISTS above is a no-op on an existing table.
    "ALTER TABLE scans ADD COLUMN IF NOT EXISTS root_span_id TEXT",
    "ALTER TABLE scans ADD COLUMN IF NOT EXISTS root_trace_id TEXT",
    "ALTER TABLE scans ADD COLUMN IF NOT EXISTS judged_at TIMESTAMP",
    """CREATE TABLE IF NOT EXISTS findings (
        scan_id         TEXT NOT NULL,
        canonical_type  TEXT NOT NULL,
        occurrences     INTEGER NOT NULL,
        max_confidence  DOUBLE,
        sensitivity     TEXT NOT NULL,
        source_engines  TEXT,
        source_models   TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS eval_scores (
        scan_id         TEXT NOT NULL,
        evaluator       TEXT NOT NULL,
        score           DOUBLE,
        label           TEXT,
        explanation     TEXT,
        evaluated_at    TIMESTAMP NOT NULL
    )""",
]


def default_db_path() -> str:
    """PII_DB_PATH or the gitignored data/ directory."""
    return os.environ.get("PII_DB_PATH", "data/pii.duckdb")


def connect(path: str | None = None) -> Any:
    """Open (creating parents) and ensure the schema exists."""
    import duckdb  # the seam: only imported here

    db_path = path or default_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(db_path)
    for stmt in _DDL:
        conn.execute(stmt)
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upsert_document(conn: Any, result: DocumentResult, s3_key: str | None) -> None:
    """Register the document once, keyed by content checksum."""
    exists = conn.execute(
        "SELECT 1 FROM documents WHERE checksum = ?", [result.checksum]
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            result.checksum, result.user_login, result.document.file_name,
            result.document.file_type, result.document.size_bytes,
            result.document.page_count, s3_key, _now(),
        ],
    )


def insert_scan(conn: Any, result: DocumentResult, latency_ms: int | None = None) -> None:
    """Persist one scan and its per-type finding rows.

    Explicit column list (not `INSERT INTO scans VALUES (...)`) so the
    schema can grow columns — root_span_id/root_trace_id/judged_at, filled
    in later by record_span()/mark_judged() — without this insert breaking.
    """
    conn.execute(
        """INSERT INTO scans
           (scan_id, checksum, pipeline_version, engine, models, session_id,
            status, result_json, latency_ms, cost_usd, started_at, ended_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            result.run.scan_id, result.checksum, result.run.pipeline_version,
            result.run.engine, json.dumps(result.run.models), result.run.session_id,
            result.document.processing_status,
            result.model_dump_json(), latency_ms, None,
            result.run.started_at, result.run.ended_at,
        ],
    )
    for f in result.findings:
        conn.execute(
            "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                result.run.scan_id, f.canonical_type, f.occurrences,
                f.max_confidence, f.sensitivity,
                json.dumps(f.source_engines), json.dumps(f.source_models),
            ],
        )


def cache_lookup(conn: Any, checksum: str, pipeline_version: str) -> DocumentResult | None:
    """The cache: a completed scan of the same bytes under the same config."""
    row = conn.execute(
        """SELECT result_json FROM scans
           WHERE checksum = ? AND pipeline_version = ? AND status = 'processed'
           ORDER BY started_at DESC LIMIT 1""",
        [checksum, pipeline_version],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return DocumentResult.model_validate_json(row[0])


def record_span(conn: Any, scan_id: str, root_span_id: str | None,
                root_trace_id: str | None) -> None:
    """Link a scan to its forwarded trace — the Arize push job's join key."""
    conn.execute(
        "UPDATE scans SET root_span_id = ?, root_trace_id = ? WHERE scan_id = ?",
        [root_span_id, root_trace_id, scan_id],
    )


def mark_judged(conn: Any, scan_id: str) -> None:
    """Record that the local judge + Arize push ran for this scan."""
    conn.execute("UPDATE scans SET judged_at = ? WHERE scan_id = ?",
                 [datetime.now(timezone.utc).replace(tzinfo=None), scan_id])


def unjudged_scans(conn: Any, limit: int = 100) -> list[tuple[str, str | None]]:
    """(scan_id, root_span_id) for processed scans not yet judged — resumable
    backlog for the push job (e.g. after a mid-run crash)."""
    return conn.execute(
        """SELECT scan_id, root_span_id FROM scans
           WHERE status = 'processed' AND judged_at IS NULL
           ORDER BY started_at LIMIT ?""",
        [limit],
    ).fetchall()
