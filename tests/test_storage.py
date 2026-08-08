"""DB seam (schema, persistence, cache semantics) and S3 key layout."""

from datetime import date

from pipeline.schemas import (
    ComplianceImpact, DocumentMeta, DocumentResult, NormalizedFinding, RunInfo,
)
from pipeline.storage import db, s3


def _result(checksum="c" * 64, pv="pv1", status="processed", scan_id="scan_1"):
    return DocumentResult(
        checksum=checksum,
        user_login="senthil",
        document=DocumentMeta(
            source_path="/x/a.txt", file_name="a.txt", file_type="txt",
            size_bytes=10, structural_class="unstructured",
            processing_status=status,
        ),
        findings=[
            NormalizedFinding(
                canonical_type="EMAIL_ADDRESS", raw_labels_seen=["email"],
                occurrences=2, chunk_ids=["chunk_0001"],
                sample_excerpts=["a@example.com"], max_confidence=0.9,
                sensitivity="medium", source_engines=["presidio"],
            )
        ],
        compliance_impact=ComplianceImpact(
            impacted_jurisdictions=[], hits=[], regime_matrix_version="1"
        ),
        run=RunInfo(scan_id=scan_id, pipeline_version=pv, engine="presidio",
                    started_at="2026-08-07T00:00:00+00:00"),
    )


def test_schema_roundtrip_and_cache_hit():
    conn = db.connect(":memory:")
    r = _result()
    db.upsert_document(conn, r, s3_key=None)
    db.insert_scan(conn, r, latency_ms=42)

    cached = db.cache_lookup(conn, r.checksum, "pv1")
    assert cached is not None
    assert cached.run.scan_id == "scan_1"
    assert cached.findings[0].canonical_type == "EMAIL_ADDRESS"


def test_cache_misses_on_pipeline_version_change():
    conn = db.connect(":memory:")
    r = _result()
    db.upsert_document(conn, r, None)
    db.insert_scan(conn, r)
    assert db.cache_lookup(conn, r.checksum, "pv2") is None


def test_failed_scans_never_serve_from_cache():
    conn = db.connect(":memory:")
    r = _result(status="failed")
    db.upsert_document(conn, r, None)
    db.insert_scan(conn, r)
    assert db.cache_lookup(conn, r.checksum, "pv1") is None


def test_document_upsert_is_idempotent():
    conn = db.connect(":memory:")
    r = _result()
    db.upsert_document(conn, r, None)
    db.upsert_document(conn, r, None)
    (count,) = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert count == 1


def test_s3_key_layout():
    d = date(2026, 8, 7)
    assert (
        s3.upload_key("senthil", d, "abc123", "resume.pdf")
        == "uploads/user_login=senthil/dt=2026-08-07/abc123/resume.pdf"
    )
    assert (
        s3.result_key("senthil", d, "abc123")
        == "results/user_login=senthil/dt=2026-08-07/abc123/result.json"
    )


def test_s3_noop_without_bucket(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    f = tmp_path / "x.txt"
    f.write_text("hi")
    outcome = s3.put_file(f, "uploads/whatever")
    assert outcome.skipped and not outcome.uploaded and not outcome.failed


def test_record_span_and_mark_judged():
    conn = db.connect(":memory:")
    r = _result()
    db.upsert_document(conn, r, None)
    db.insert_scan(conn, r)

    db.record_span(conn, r.run.scan_id, "span_abc", "trace_xyz")
    row = conn.execute(
        "SELECT root_span_id, root_trace_id, judged_at FROM scans WHERE scan_id = ?",
        [r.run.scan_id],
    ).fetchone()
    assert row[0] == "span_abc" and row[1] == "trace_xyz" and row[2] is None

    db.mark_judged(conn, r.run.scan_id)
    judged_at = conn.execute(
        "SELECT judged_at FROM scans WHERE scan_id = ?", [r.run.scan_id]
    ).fetchone()[0]
    assert judged_at is not None


def test_unjudged_scans_excludes_judged_and_non_processed():
    conn = db.connect(":memory:")
    processed = _result(scan_id="s_processed", status="processed")
    failed = _result(scan_id="s_failed", checksum="d" * 64, status="failed")
    already_judged = _result(scan_id="s_judged", checksum="e" * 64, status="processed")
    for r in (processed, failed, already_judged):
        db.upsert_document(conn, r, None)
        db.insert_scan(conn, r)
    db.mark_judged(conn, already_judged.run.scan_id)

    pending = [scan_id for scan_id, _ in db.unjudged_scans(conn)]
    assert pending == ["s_processed"]  # not failed (nothing to judge), not already-judged


def test_s3_client_uses_path_style_addressing_when_configured(monkeypatch):
    # MinIO (and most self-hosted S3-compatible stores) rejects
    # virtual-hosted-style requests; regression guard for that fix.
    monkeypatch.setenv("OBJECT_STORE_ENDPOINT", "https://minio.example.com")
    monkeypatch.setenv("OBJECT_STORE_FORCE_PATH_STYLE", "true")
    client = s3._client()
    assert client.meta.config.s3["addressing_style"] == "path"


def test_s3_client_defaults_to_virtual_style_without_the_flag(monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_ENDPOINT", "https://s3.amazonaws.com")
    monkeypatch.delenv("OBJECT_STORE_FORCE_PATH_STYLE", raising=False)
    client = s3._client()
    assert (client.meta.config.s3 or {}).get("addressing_style") != "path"
