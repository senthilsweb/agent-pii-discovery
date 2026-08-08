"""Judge layer L1: code checks, calibration determinism, agreement math."""

import pytest

from evals.judge.calibrate import (
    BUILDERS, build_r2_cases, build_r3_cases, build_r5_cases, build_r6_cases,
    run_calibration,
)
from evals.judge.checks import check_grounding, check_span_fidelity
from evals.judge.llm_judge import resolve_judge_model
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
    assert check_grounding(_result(["priya@example.com", "Priya  Raman"]), TEXT).passed


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


def test_case_builders_deterministic():
    for name, builder in BUILDERS.items():
        a, b = builder(20), builder(20)
        assert [(c.payload, c.expected) for c in a] == \
               [(c.payload, c.expected) for c in b], name


def test_r2_cases_balanced_with_context():
    cases = build_r2_cases(30)
    assert len(cases) == 30
    assert sum(1 for c in cases if not c.expected) >= 10
    assert any(c.payload.get("context") for c in cases)


def test_r3_cases_pair_full_and_holdout():
    cases = build_r3_cases(10)
    assert any(c.expected for c in cases) and any(not c.expected for c in cases)
    holdout = next(c for c in cases if c.expected)
    full = next(c for c in cases if c.source == holdout.source and not c.expected)
    assert len(holdout.payload["detected"]) < len(full.payload["detected"])


def test_r5_cases_pair_defensible_and_not():
    cases = build_r5_cases(40)
    lows = [c for c in cases if c.payload["sensitivity"] == "low"]
    assert lows and all(not c.expected for c in lows)


def test_r6_cases_honest_vs_obeyed():
    cases = build_r6_cases(10)
    assert any(c.expected for c in cases) and any(not c.expected for c in cases)
    obeyed_zero = [c for c in cases if c.expected and "none" in c.payload["report"]]
    assert obeyed_zero, "zero-findings obeyed variant must exist"


class OracleClient:
    """Fake Anthropic client answering from a per-call truth list."""

    def __init__(self, answers):
        outer = self
        self._answers = list(answers)

        class _Messages:
            def parse(self, **kwargs):
                truth = outer._answers.pop(0)
                out_type = kwargs["output_format"]
                fields = out_type.model_fields
                payload = {"reason": "oracle",
                           ("correct" if "correct" in fields else "answer"): truth}
                class M:  # noqa: N801
                    parsed_output = out_type(**payload)
                return M()

        self.messages = _Messages()


@pytest.mark.parametrize("criterion", ["R2", "R3", "R5", "R6"])
def test_agreement_math_perfect_and_flipped(criterion):
    cases = BUILDERS[criterion](12)
    perfect = run_calibration(criterion, cases, model="fake",
                              client=OracleClient([c.expected for c in cases]))
    assert perfect["agreement"] == 1.0 and perfect["passes"]
    flipped = run_calibration(criterion, cases, model="fake",
                              client=OracleClient([not c.expected for c in cases]))
    assert flipped["agreement"] == 0.0 and not flipped["passes"]


def test_judge_model_resolution(monkeypatch):
    monkeypatch.setenv("MODEL_JUDGE", "claude-opus-5")
    assert resolve_judge_model() == "claude-opus-5"
    monkeypatch.delenv("MODEL_JUDGE")
    monkeypatch.delenv("MODEL", raising=False)
    with pytest.raises(RuntimeError):
        resolve_judge_model()
