"""Judge runner — score one persisted scan and write eval_scores (Phase 5).

Runs the deterministic checks (R1 grounding, R4 span fidelity) at 100% and
the calibrated LLM judges (R2 type accuracy, R5 sensitivity sanity) over the
scan's findings (capped per scan to bound judge cost). Any HARD fail (R1 or
any R2 incorrect) labels the scan `flagged` — the review-queue signal.

This is the local complement to Arize online-eval tasks: same criteria, same
rubric, writes to the operational DB so "show me flagged scans" needs no
Arize round-trip.

Usage:
    MODEL_JUDGE=claude-opus-5 python -m evals.judge.runner \
        --scan-id <id> --doc <source document> [--db data/pii.duckdb]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.judge.checks import check_grounding, check_span_fidelity
from evals.judge.llm_judge import judge_sensitivity, judge_type_accuracy
from pipeline.chunking import chunk_text
from pipeline.schemas import DocumentResult
from pipeline.storage import db

MAX_JUDGED_FINDINGS = 10


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _record(conn, scan_id, evaluator, score, label, explanation):
    conn.execute("INSERT INTO eval_scores VALUES (?, ?, ?, ?, ?, ?)",
                 [scan_id, evaluator, score, label, explanation[:500], _now()])


def judge_scan(conn, result: DocumentResult, source_text: str,
               model: str | None = None, client=None) -> dict:
    """Run R1/R4 checks + R2/R5 judges; persist eval_scores; return summary."""
    scan_id = result.run.scan_id
    hard_fail = False

    r1 = check_grounding(result, source_text)
    hard_fail |= not r1.passed
    _record(conn, scan_id, "R1_grounding", 1.0 if r1.passed else 0.0,
            "pass" if r1.passed else "fail", "; ".join(r1.failures) or "all grounded")

    chunks = {c.chunk_id: c.text for c in chunk_text(source_text)}
    r4 = check_span_fidelity(result, chunks)
    _record(conn, scan_id, "R4_span_fidelity", 1.0 if r4.passed else 0.0,
            "pass" if r4.passed else "warn", "; ".join(r4.failures) or "all spans bound")

    judged = result.findings[:MAX_JUDGED_FINDINGS]
    r2_correct = 0
    for f in judged:
        excerpt = f.sample_excerpts[0] if f.sample_excerpts else ""
        v = judge_type_accuracy(excerpt, f.canonical_type, model=model, client=client)
        r2_correct += v.correct
        if not v.correct:
            hard_fail = True
            _record(conn, scan_id, "R2_type_accuracy", 0.0, "fail",
                    f"{f.canonical_type}: {v.reason}")
    r2_score = r2_correct / len(judged) if judged else 1.0
    _record(conn, scan_id, "R2_type_accuracy", r2_score,
            "pass" if r2_score == 1.0 else "fail", f"{r2_correct}/{len(judged)} correct")

    r5_ok = 0
    for f in judged:
        v = judge_sensitivity(f.canonical_type, f.sensitivity, model=model, client=client)
        r5_ok += v.answer
        if not v.answer:
            _record(conn, scan_id, "R5_sensitivity", 0.0, "warn",
                    f"{f.canonical_type}={f.sensitivity}: {v.reason}")
    r5_score = r5_ok / len(judged) if judged else 1.0
    _record(conn, scan_id, "R5_sensitivity", r5_score,
            "pass" if r5_score == 1.0 else "warn", f"{r5_ok}/{len(judged)} defensible")

    label = "flagged" if hard_fail else "pass"
    _record(conn, scan_id, "overall", 0.0 if hard_fail else 1.0, label,
            "HARD fail → review queue" if hard_fail else "all HARD criteria green")
    return {"scan_id": scan_id, "label": label,
            "R1": r1.passed, "R4": r4.passed, "R2": r2_score, "R5": r5_score,
            "judged_findings": len(judged)}


def flagged_queue(conn) -> list[tuple]:
    """The review queue: scans whose latest overall verdict is flagged."""
    return conn.execute(
        """SELECT scan_id, MAX(evaluated_at) FROM eval_scores
           WHERE evaluator = 'overall' AND label = 'flagged'
           GROUP BY scan_id ORDER BY 2 DESC""").fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge one persisted scan")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--doc", required=True, help="source document (text) path")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    conn = db.connect(args.db)
    row = conn.execute("SELECT result_json FROM scans WHERE scan_id = ?",
                       [args.scan_id]).fetchone()
    if not row or not row[0]:
        raise SystemExit(f"no persisted result for {args.scan_id}")
    result = DocumentResult.model_validate_json(row[0])
    summary = judge_scan(conn, result, Path(args.doc).read_text())
    print(json.dumps(summary, indent=2))
    return 0 if summary["label"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
