"""Judge runner: eval_scores rows, flagging semantics, review queue."""

from evals.judge.runner import flagged_queue, judge_scan
from pipeline.schemas import (
    ComplianceImpact, DocumentMeta, DocumentResult, NormalizedFinding, RunInfo,
)
from pipeline.storage import db
from tests.test_judge import OracleClient

TEXT = "Contact Priya Raman at priya@example.com for details."


def _result(scan_id, excerpts):
    return DocumentResult(
        checksum="c" * 64, user_login="u",
        document=DocumentMeta(source_path="/x", file_name="x.txt", file_type="txt",
                              size_bytes=1, structural_class="unstructured",
                              processing_status="processed"),
        findings=[NormalizedFinding(
            canonical_type="EMAIL_ADDRESS", raw_labels_seen=["email"], occurrences=1,
            chunk_ids=["chunk_0001"], sample_excerpts=[e],
            max_confidence=0.9, sensitivity="medium", source_engines=["genai"])
            for e in excerpts],
        compliance_impact=ComplianceImpact(impacted_jurisdictions=[], hits=[],
                                           regime_matrix_version="1"),
        run=RunInfo(scan_id=scan_id, pipeline_version="p", engine="genai_only",
                    started_at="2026-08-08T00:00:00+00:00"),
    )


def test_clean_scan_passes_and_records_scores():
    conn = db.connect(":memory:")
    # 1 finding → 1 R2 call + 1 R5 call, both positive
    summary = judge_scan(conn, _result("s1", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([True, True]))
    assert summary["label"] == "pass" and summary["R1"] and summary["R2"] == 1.0
    evaluators = {r[0] for r in conn.execute(
        "SELECT DISTINCT evaluator FROM eval_scores").fetchall()}
    assert {"R1_grounding", "R4_span_fidelity", "R2_type_accuracy",
            "R5_sensitivity", "overall"} <= evaluators
    assert flagged_queue(conn) == []


def test_ungrounded_finding_flags_without_any_judge_call():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s2", ["attacker@evil.example"]), TEXT,
                         model="fake", client=OracleClient([True, True]))
    assert not summary["R1"] and summary["label"] == "flagged"
    assert [q[0] for q in flagged_queue(conn)] == ["s2"]


def test_r2_incorrect_type_flags():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s3", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([False, True]))
    assert summary["R2"] == 0.0 and summary["label"] == "flagged"


def test_r5_indefensible_warns_but_does_not_flag():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s4", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([True, False]))
    assert summary["R5"] == 0.0 and summary["label"] == "pass"  # R5 is SOFT
