"""Judge layer L1: code checks, calibration determinism, agreement math."""

import pytest

from evals.judge.calibrate import build_cases, run_calibration
from evals.judge.checks import check_grounding, check_span_fidelity
from evals.judge.llm_judge import TypeVerdict, resolve_judge_model
from pipeline.schemas import (
    ComplianceImpact, DocumentMeta, DocumentResult, NormalizedFinding, RunInfo, Span,
)

TEXT = "Contact Priya Raman at priya@example.com for details."


def _result(excerpts, spans=None):
    return DocumentResult(
        checksum="c" * 64, user_login="u",
        document=DocumentMeta(source_path="/x", file_name="x.txt", file_type="txt",
                              size_bytes=1, structural_class="unstructured",
                              processing_status="processed"),
        findings=[NormalizedFinding(
            canonical_type="EMAIL_ADDRESS", raw_labels_seen=["email"], occurrences=1,
            chunk_ids=["chunk_0001"], sample_excerpts=excerpts, spans=spans or [],
            max_confidence=0.9, sensitivity="medium", source_engines=["genai"])],
        compliance_impact=ComplianceImpact(impacted_jurisdictions=[], hits=[],
                                           regime_matrix_version="1"),
        run=RunInfo(scan_id="s", pipeline_version="p", engine="genai_only",
                    started_at="2026-08-08T00:00:00+00:00"),
    )


def test_r1_grounded_passes_and_normalizes_whitespace():
    v = check_grounding(_result(["priya@example.com", "Priya  Raman"]), TEXT)
    assert v.passed


def test_r1_fabricated_excerpt_fails():
    v = check_grounding(_result(["attacker@evil.example"]), TEXT)
    assert not v.passed and "EMAIL_ADDRESS" in v.failures[0]


def test_r4_span_within_tolerance_passes():
    span = Span(chunk_id="chunk_0001", start=23, end=40)
    v = check_span_fidelity(_result(["priya@example.com"], [span]), {"chunk_0001": TEXT})
    assert v.passed


def test_r4_wrong_span_fails():
    span = Span(chunk_id="chunk_0001", start=0, end=7)
    v = check_span_fidelity(_result(["priya@example.com"], [span]), {"chunk_0001": TEXT})
    assert not v.passed


def test_calibration_cases_deterministic_and_balanced():
    a, b = build_cases(30), build_cases(30)
    assert [(c.excerpt, c.candidate_type) for c in a] == [(c.excerpt, c.candidate_type) for c in b]
    assert len(a) == 30
    negatives = [c for c in a if not c.expected_correct]
    assert len(negatives) >= 10  # meaningful negative coverage


class OracleJudge:
    """Fake client that answers from the cases' own ground truth."""

    def __init__(self, cases):
        truth = {(repr(c.excerpt), c.candidate_type): c.expected_correct for c in cases}
        outer = self

        class _Messages:
            def parse(self, **kwargs):
                content = kwargs["messages"][0]["content"]
                excerpt_repr, candidate = content.split("Excerpt: ", 1)[1].rsplit(
                    "\nCandidate type: ", 1)
                class M:  # noqa: N801
                    parsed_output = TypeVerdict(
                        correct=outer._truth[(excerpt_repr, candidate)], reason="oracle")
                return M()

        self._truth = truth
        self.messages = _Messages()


def test_agreement_math_with_perfect_judge():
    cases = build_cases(20)
    summary = run_calibration(cases, model="fake", client=OracleJudge(cases))
    assert summary["agreement"] == 1.0 and summary["passes"]


def test_agreement_math_flags_a_wrong_judge():
    cases = build_cases(20)
    oracle = OracleJudge(cases)
    flipped = {k: not v for k, v in oracle._truth.items()}
    oracle._truth = flipped
    summary = run_calibration(cases, model="fake", client=oracle)
    assert summary["agreement"] == 0.0 and not summary["passes"]


def test_judge_model_resolution(monkeypatch):
    monkeypatch.setenv("MODEL_JUDGE", "claude-opus-5")
    assert resolve_judge_model() == "claude-opus-5"
    monkeypatch.delenv("MODEL_JUDGE")
    monkeypatch.delenv("MODEL", raising=False)
    with pytest.raises(RuntimeError):
        resolve_judge_model()
