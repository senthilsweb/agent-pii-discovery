"""Judge runner: eval_scores rows, flagging semantics, review queue."""

from evals.judge.runner import ALL_CRITERIA, flagged_queue, judge_scan
from pipeline.schemas import (
    ComplianceImpact, DocumentMeta, DocumentResult, NormalizedFinding, RunInfo,
)
from pipeline.storage import db
from tests.test_judge import OracleClient

TEXT = "Contact Priya Raman at priya@example.com for details."
R2_R5_ONLY = frozenset({"R1", "R2", "R4", "R5"})


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


def _scores(conn, scan_id):
    return {row[0]: (row[1], row[2]) for row in conn.execute(
        "SELECT evaluator, score, label FROM eval_scores WHERE scan_id = ?", [scan_id]
    ).fetchall()}


def test_clean_scan_passes_and_records_scores():
    conn = db.connect(":memory:")
    # 1 finding → 1 R2 call + 1 R5 call, both positive
    summary = judge_scan(conn, _result("s1", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([True, True]),
                         criteria=R2_R5_ONLY)
    assert summary["label"] == "pass"
    scores = _scores(conn, "s1")
    assert scores["R1_grounding"] == (1.0, "pass")
    assert scores["R2_type_accuracy"][0] == 1.0
    assert scores["R5_sensitivity"][0] == 1.0
    assert flagged_queue(conn) == []


def test_ungrounded_finding_flags_without_any_judge_call():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s2", ["attacker@evil.example"]), TEXT,
                         model="fake", client=OracleClient([True, True]),
                         criteria=R2_R5_ONLY)
    scores = _scores(conn, "s2")
    assert scores["R1_grounding"] == (0.0, "fail")
    assert summary["label"] == "flagged"
    assert [q[0] for q in flagged_queue(conn)] == ["s2"]


def test_r2_incorrect_type_flags():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s3", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([False, True]),
                         criteria=R2_R5_ONLY)
    assert _scores(conn, "s3")["R2_type_accuracy"][0] == 0.0
    assert summary["label"] == "flagged"


def test_r5_indefensible_warns_but_does_not_flag():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s4", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([True, False]),
                         criteria=R2_R5_ONLY)
    assert _scores(conn, "s4")["R5_sensitivity"][0] == 0.0
    assert summary["label"] == "pass"  # R5 is SOFT


def test_criteria_selector_limits_what_runs():
    conn = db.connect(":memory:")
    judge_scan(conn, _result("s5", ["priya@example.com"]), TEXT,
              criteria=frozenset({"R1", "R4"}))  # code checks only, no judge calls
    evaluators = {r[0] for r in conn.execute(
        "SELECT evaluator FROM eval_scores WHERE scan_id = ?", ["s5"]).fetchall()}
    assert evaluators == {"R1_grounding", "R4_span_fidelity", "overall"}


def test_all_criteria_run_end_to_end():
    conn = db.connect(":memory:")
    # R1, R4 (free) + R2, R3, R5, R6 (1 finding each) = 6 judge calls total
    judge_scan(conn, _result("s6", ["priya@example.com"]), TEXT,
              model="fake", client=OracleClient([True, False, True, False]),
              criteria=ALL_CRITERIA)
    evaluators = {r[0] for r in conn.execute(
        "SELECT evaluator FROM eval_scores WHERE scan_id = ?", ["s6"]).fetchall()}
    assert evaluators == {"R1_grounding", "R2_type_accuracy", "R3_coverage",
                          "R4_span_fidelity", "R5_sensitivity", "R6_injection", "overall"}


def test_r6_obeyed_flags_the_scan():
    conn = db.connect(":memory:")
    summary = judge_scan(conn, _result("s7", ["priya@example.com"]), TEXT,
                         model="fake", client=OracleClient([True, True, True, True]),
                         criteria=frozenset({"R1", "R6"}))
    assert _scores(conn, "s7")["R6_injection"] == (0.0, "fail")
    assert summary["label"] == "flagged"
