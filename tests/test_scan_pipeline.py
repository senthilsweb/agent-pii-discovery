"""End-to-end deterministic pipeline over real corpus fixtures.

Still L1: the Presidio analyzer is a fake built from each fixture's own
labels.json, so the test exercises the full trajectory logic, span mapping,
normalization, compliance, persistence, and caching — without spaCy, network,
or keys. (Real-engine P/R/F1 is Phase 2's L2 gate.)
"""

import json
from pathlib import Path

import pytest

from pipeline.engine import resolve_pii_engine
from pipeline.scan import scan_document
from pipeline.storage import db
from tests.conftest import FakeAnalyzer, FakeHit

CORPUS = Path(__file__).resolve().parent.parent / "evals" / "data"


def _fixture(fixture_id: str) -> tuple[Path, dict]:
    d = CORPUS / fixture_id
    return next(d.glob("document.*")), json.loads((d / "labels.json").read_text())


def _analyzer_from_labels(doc_path: Path, labels: dict) -> FakeAnalyzer:
    text = doc_path.read_text()
    hits = []
    for e in labels["entities"]:
        if e.get("start") is not None:
            assert text[e["start"]:e["end"]] == e["value"]  # corpus invariant
            hits.append(FakeHit(e["canonical_type"], e["start"], e["end"]))
    return FakeAnalyzer(hits)


def test_engine_resolution_required(monkeypatch):
    monkeypatch.delenv("PII_ENGINE", raising=False)
    with pytest.raises(RuntimeError, match="PII_ENGINE is required"):
        resolve_pii_engine()
    monkeypatch.setenv("PII_ENGINE", "openai_privacy_filter")
    with pytest.raises(RuntimeError, match="out of scope"):
        resolve_pii_engine()


def test_full_scan_on_prose_fixture():
    doc, labels = _fixture("synthetic_prose_01")
    conn = db.connect(":memory:")
    result = scan_document(doc, user_login="tester", engine="presidio",
                           conn=conn, analyzer=_analyzer_from_labels(doc, labels))
    assert result.document.processing_status == "processed"
    assert result.document.chunk_count >= 1

    # Every labeled type surfaced, and every excerpt is grounded in the doc.
    text = doc.read_text()
    found_types = {f.canonical_type for f in result.findings}
    labeled_types = {e["canonical_type"] for e in labels["entities"]}
    assert labeled_types <= found_types
    for f in result.findings:
        for excerpt in f.sample_excerpts:
            assert excerpt in text

    # Compliance came from the matrix, not thin air.
    assert result.compliance_impact.impacted_jurisdictions


def test_columnar_fixture_is_rejected_without_scanning():
    doc, labels = _fixture("columnar_01")
    conn = db.connect(":memory:")

    class Exploding:
        def analyze(self, text, language):  # pragma: no cover
            raise AssertionError("scan tools must not run on the reject path")

    result = scan_document(doc, user_login="tester", engine="presidio",
                           conn=conn, analyzer=Exploding())
    assert result.document.processing_status == "skipped_out_of_scope"
    assert labels["expect"] == "skipped_out_of_scope"
    assert result.findings == []


def test_clean_fixture_yields_zero_findings():
    doc, labels = _fixture("clean_01")
    conn = db.connect(":memory:")
    result = scan_document(doc, user_login="tester", engine="presidio",
                           conn=conn, analyzer=FakeAnalyzer([]))
    assert result.document.processing_status == "processed"
    assert result.findings == []
    assert result.compliance_impact.impacted_jurisdictions == []


def test_second_scan_hits_cache_and_runs_nothing():
    doc, labels = _fixture("synthetic_prose_02")
    conn = db.connect(":memory:")
    first = scan_document(doc, user_login="tester", engine="presidio",
                          conn=conn, analyzer=_analyzer_from_labels(doc, labels))

    class Exploding:
        def analyze(self, text, language):  # pragma: no cover
            raise AssertionError("cache hit must not scan")

    second = scan_document(doc, user_login="tester", engine="presidio",
                           conn=conn, analyzer=Exploding())
    assert second.run.scan_id == first.run.scan_id  # served from cache


def test_genai_engines_fail_loudly_until_phase_3(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello world, nothing here")
    with pytest.raises(RuntimeError, match="Phase 3"):
        scan_document(f, user_login="t", engine="genai_only", conn=db.connect(":memory:"))
