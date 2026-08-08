"""L3 judge calibration — measure the judge against labeled cases (rubrics §3).

Cases derive deterministically from the corpus sidecars, where ground truth
is exact: a labeled (value, type) pair is a positive case (expect
correct=True); the same value paired with a deliberately wrong type is a
negative case (expect correct=False). A judge criterion is trusted for live
traffic only at ≥90% agreement.

Usage (spends judge tokens — a 30-case run on haiku is ~pennies):
    MODEL_JUDGE=claude-haiku-4-5 python -m evals.judge.calibrate [--cases 30]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from evals.judge.llm_judge import judge_type_accuracy, resolve_judge_model

SEED = 20260808
CORPUS = Path(__file__).resolve().parent.parent / "data"

# Wrong-type pairings that are genuinely wrong, not debatable neighbours.
FAR_TYPES = {
    "EMAIL_ADDRESS": "GOVERNMENT_ID_PASSPORT", "PHONE_NUMBER": "HEALTH_CONDITION",
    "GOVERNMENT_ID_SSN": "GEOLOCATION", "CREDIT_CARD_NUMBER": "RELIGIOUS_BELIEF",
    "IP_ADDRESS": "PERSON_NAME", "PERSON_NAME": "IBAN",
    "PHYSICAL_ADDRESS": "MAC_ADDRESS", "DATE_OF_BIRTH": "CRYPTO_WALLET_ADDRESS",
}


@dataclass
class Case:
    excerpt: str
    candidate_type: str
    expected_correct: bool
    source: str


def build_cases(limit: int) -> list[Case]:
    """Deterministic positive/negative cases from the corpus sidecars."""
    entities = []
    for labels_file in sorted(CORPUS.glob("synthetic_prose_*/labels.json")):
        data = json.loads(labels_file.read_text())
        for e in data["entities"]:
            entities.append((e["value"], e["canonical_type"], labels_file.parent.name))

    rng = random.Random(SEED)
    rng.shuffle(entities)
    cases: list[Case] = []
    for value, ctype, src in entities:
        if len(cases) >= limit:
            break
        cases.append(Case(value, ctype, True, src))
        wrong = FAR_TYPES.get(ctype)
        if wrong and len(cases) < limit:
            cases.append(Case(value, wrong, False, src))
    return cases


def run_calibration(cases: list[Case], model: str | None = None, client=None) -> dict:
    """Score the judge; returns the agreement summary."""
    model = model or resolve_judge_model()
    agree = 0
    disagreements = []
    for c in cases:
        verdict = judge_type_accuracy(c.excerpt, c.candidate_type,
                                      model=model, client=client)
        if verdict.correct == c.expected_correct:
            agree += 1
        else:
            disagreements.append({
                "excerpt": c.excerpt[:60], "candidate": c.candidate_type,
                "expected_correct": c.expected_correct, "judge_reason": verdict.reason,
            })
    return {
        "criterion": "R2_type_accuracy",
        "judge_model": model,
        "cases": len(cases),
        "agreement": round(agree / len(cases), 4) if cases else 0.0,
        "threshold": 0.90,
        "passes": bool(cases) and agree / len(cases) >= 0.90,
        "disagreements": disagreements,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the R2 judge (L3)")
    parser.add_argument("--cases", type=int, default=30)
    args = parser.parse_args(argv)
    summary = run_calibration(build_cases(args.cases))
    print(json.dumps(summary, indent=2))
    return 0 if summary["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
