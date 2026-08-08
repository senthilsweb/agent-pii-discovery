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
