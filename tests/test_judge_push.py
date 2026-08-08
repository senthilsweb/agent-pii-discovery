"""Push job: sampling determinism, cost gating, dataframe shape, env-gating."""

import pytest

from evals.judge.push import (
    CODE_CRITERIA, LLM_CRITERIA, judge_and_push, push_to_arize,
    resolve_sample_rate, should_sample,
)
from pipeline.schemas import (
    ComplianceImpact, DocumentMeta, DocumentResult, NormalizedFinding, RunInfo,
)
from pipeline.storage import db
from tests.test_judge import OracleClient


def _result(scan_id, status="processed", excerpts=("priya@example.com",)):
    return DocumentResult(
        checksum="c" * 64, user_login="u",
        document=DocumentMeta(source_path="/x", file_name="x.txt", file_type="txt",
                              size_bytes=1, structural_class="unstructured",
                              processing_status=status),
        findings=[NormalizedFinding(
            canonical_type="EMAIL_ADDRESS", raw_labels_seen=["email"], occurrences=1,
            chunk_ids=["chunk_0001"], sample_excerpts=[e],
            max_confidence=0.9, sensitivity="medium", source_engines=["genai"])
            for e in excerpts] if status == "processed" else [],
        compliance_impact=ComplianceImpact(impacted_jurisdictions=[], hits=[],
                                           regime_matrix_version="1"),
        run=RunInfo(scan_id=scan_id, pipeline_version="p", engine="genai_only",
                    started_at="2026-08-08T00:00:00+00:00"),
    )


# --- sampling ---------------------------------------------------------------

def test_sample_rate_env_default_and_clamp(monkeypatch):
    monkeypatch.delenv("PII_JUDGE_SAMPLE_RATE", raising=False)
    assert resolve_sample_rate() == 0.25
    monkeypatch.setenv("PII_JUDGE_SAMPLE_RATE", "1.5")
    assert resolve_sample_rate() == 1.0
    monkeypatch.setenv("PII_JUDGE_SAMPLE_RATE", "-1")
    assert resolve_sample_rate() == 0.0
    monkeypatch.setenv("PII_JUDGE_SAMPLE_RATE", "not-a-number")
    assert resolve_sample_rate() == 0.25


def test_sampling_is_deterministic_per_scan_id():
    a = should_sample("scan_abc123", 0.25)
    b = should_sample("scan_abc123", 0.25)
    assert a == b  # same scan_id → same decision, every time


def test_sampling_rate_zero_and_one_are_absolute():
    assert should_sample("scan_anything", 0.0) is False
    assert should_sample("scan_anything", 1.0) is True


def test_sampling_roughly_matches_rate_over_many_ids():
    sampled = sum(should_sample(f"scan_{i}", 0.25) for i in range(2000))
    assert 400 < sampled < 600  # ~25% of 2000, generous tolerance


def test_criteria_partition_is_exhaustive_and_disjoint():
    assert CODE_CRITERIA | LLM_CRITERIA == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert CODE_CRITERIA & LLM_CRITERIA == set()


# --- judge_and_push orchestration -------------------------------------------

def test_skips_non_processed_scans(tmp_path):
    conn = db.connect(":memory:")
    doc = tmp_path / "x.txt"
    doc.write_text("hello")
    summary = judge_and_push(_result("s1", status="skipped_out_of_scope"), doc,
                             "span_abc", conn)
    assert not summary["judged"] and "nothing to judge" in summary["reason"]


def test_forced_sample_rate_one_runs_all_criteria(tmp_path, monkeypatch):
    monkeypatch.delenv("ARIZE_SPACE_ID", raising=False)
    monkeypatch.delenv("ARIZE_API_KEY", raising=False)
    conn = db.connect(":memory:")
    doc = tmp_path / "x.txt"
    doc.write_text("Contact Priya Raman at priya@example.com for details.")
    summary = judge_and_push(
        _result("s2"), doc, "span_abc", conn,
        model="fake", client=OracleClient([True, False, True, False]),
        sample_rate=1.0,
    )
    assert summary["judged"] and summary["sampled"]
    assert set(summary["criteria_run"]) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert not summary["pushed"]  # no Arize creds configured — logged, not raised


def test_forced_sample_rate_zero_runs_only_code_checks(tmp_path):
    conn = db.connect(":memory:")
    doc = tmp_path / "x.txt"
    doc.write_text("Contact Priya Raman at priya@example.com for details.")
    summary = judge_and_push(_result("s3"), doc, "span_abc", conn, sample_rate=0.0)
    assert summary["judged"] and not summary["sampled"]
    assert set(summary["criteria_run"]) == {"R1", "R4"}


def test_marks_judged_in_db(tmp_path):
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO scans (scan_id, checksum, pipeline_version, engine, status, started_at) "
        "VALUES ('s4', 'c', 'p', 'genai_only', 'processed', '2026-08-08T00:00:00')"
    )
    doc = tmp_path / "x.txt"
    doc.write_text("Contact Priya Raman at priya@example.com for details.")
    judge_and_push(_result("s4"), doc, "span_abc", conn, sample_rate=0.0)
    row = conn.execute("SELECT judged_at FROM scans WHERE scan_id = 's4'").fetchone()
    assert row[0] is not None


def test_no_root_span_id_still_judges_but_does_not_push(tmp_path):
    conn = db.connect(":memory:")
    doc = tmp_path / "x.txt"
    doc.write_text("Contact Priya Raman at priya@example.com for details.")
    summary = judge_and_push(_result("s5"), doc, None, conn, sample_rate=0.0)
    assert summary["judged"] and not summary["pushed"]


def test_missing_document_degrades_to_empty_source_text(tmp_path):
    conn = db.connect(":memory:")
    missing = tmp_path / "does_not_exist.txt"
    summary = judge_and_push(_result("s6"), missing, "span_abc", conn, sample_rate=0.0)
    # R1/R4 still "run" against empty text (everything fails grounding) rather
    # than crashing the scan.
    assert summary["judged"]


# --- Arize push (env-gated) --------------------------------------------------

def test_push_without_arize_env_is_a_warning_not_a_crash(monkeypatch):
    monkeypatch.delenv("ARIZE_SPACE_ID", raising=False)
    monkeypatch.delenv("ARIZE_API_KEY", raising=False)
    conn = db.connect(":memory:")
    assert push_to_arize(conn, "s1", "span_abc", {"eval.R1_grounding.label": "pass"}) is False


def test_push_calls_arize_client_with_expected_shape(monkeypatch):
    monkeypatch.setenv("ARIZE_SPACE_ID", "space123")
    monkeypatch.setenv("ARIZE_API_KEY", "key123")
    monkeypatch.setenv("ARIZE_PROJECT_NAME", "agent-pii-discovery")

    calls = {}

    class FakeSpans:
        def update_evaluations(self, space_id, project_name, dataframe):
            calls["space_id"] = space_id
            calls["project_name"] = project_name
            calls["rows"] = dataframe.to_dict("records")

    class FakeArizeClient:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.spans = FakeSpans()

    import sys
    import types

    fake_module = types.ModuleType("arize")
    fake_module.ArizeClient = FakeArizeClient
    monkeypatch.setitem(sys.modules, "arize", fake_module)

    conn = db.connect(":memory:")
    row_map = {"eval.R1_grounding.label": "pass", "eval.R1_grounding.score": 1.0,
              "eval.R1_grounding.explanation": "all grounded"}
    pushed = push_to_arize(conn, "s1", "span_abc123", row_map)

    assert pushed is True
    assert calls["api_key"] == "key123"
    assert calls["space_id"] == "space123"
    assert calls["project_name"] == "agent-pii-discovery"
    (row,) = calls["rows"]
    assert row["context.span_id"] == "span_abc123"
    assert row["eval.R1_grounding.label"] == "pass"
