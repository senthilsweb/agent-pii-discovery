"""Judge runner — score one persisted scan and write eval_scores (Phase 5).

Runs R1 grounding + R4 span fidelity (deterministic code checks, free) at
100%, and the four LLM judges (R2 type accuracy, R3 coverage, R5 sensitivity,
R6 injection) when selected via `criteria` — the sampling decision belongs to
the caller (`evals/judge/push.py`), not here. Any HARD fail (R1, any R2
incorrect, or R6) labels the scan `flagged` — the review-queue signal.

This is the local complement to Arize: same criteria, same rubric, writes to
the operational DB so "show me flagged scans" needs no Arize round-trip, and
the same rows feed the push job's Arize dataframe (evals/judge/push.py).

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
from evals.judge.llm_judge import (
    judge_coverage, judge_injection_live, judge_sensitivity, judge_type_accuracy,
)
from pipeline.chunking import chunk_text
from pipeline.schemas import DocumentResult
from pipeline.storage import db

MAX_JUDGED_FINDINGS = 10
CONTEXT_RADIUS = 80  # chars either side of a span, for R2's optional context
PASSAGE_CAP = 4000   # chars of source text sent to R3/R6 (cost bound)
ALL_CRITERIA = frozenset({"R1", "R2", "R3", "R4", "R5", "R6"})


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _record(conn, scan_id, evaluator, score, label, explanation):
    conn.execute("INSERT INTO eval_scores VALUES (?, ?, ?, ?, ?, ?)",
                 [scan_id, evaluator, score, label, explanation[:500], _now()])


def _context_for(finding, chunks: dict[str, str]) -> str | None:
    """Surrounding text for R2 — best-effort; None if no usable span."""
    if not finding.spans:
        return None
    span = finding.spans[0]
    text = chunks.get(span.chunk_id)
    if text is None:
        return None
    lo, hi = max(0, span.start - CONTEXT_RADIUS), min(len(text), span.end + CONTEXT_RADIUS)
    return text[lo:hi]


def judge_scan(conn, result: DocumentResult, source_text: str,
               model: str | None = None, client=None,
               criteria: frozenset[str] | None = None) -> dict:
    """Run the selected criteria; persist eval_scores; return a summary.

    `criteria` defaults to all six. R1/R4 are cheap and near-always included;
    the caller (push.py) typically passes a reduced set to control LLM cost.
    """
    criteria = criteria if criteria is not None else ALL_CRITERIA
    scan_id = result.run.scan_id
    hard_fail = False
    ran: dict[str, bool] = {}

    chunks = {c.chunk_id: c.text for c in chunk_text(source_text)} if source_text else {}

    if "R1" in criteria:
        r1 = check_grounding(result, source_text)
        hard_fail |= not r1.passed
        _record(conn, scan_id, "R1_grounding", 1.0 if r1.passed else 0.0,
                "pass" if r1.passed else "fail", "; ".join(r1.failures) or "all grounded")
        ran["R1"] = True

    if "R4" in criteria:
        r4 = check_span_fidelity(result, chunks)
        _record(conn, scan_id, "R4_span_fidelity", 1.0 if r4.passed else 0.0,
                "pass" if r4.passed else "warn", "; ".join(r4.failures) or "all spans bound")
        ran["R4"] = True

    judged = result.findings[:MAX_JUDGED_FINDINGS]

    if "R2" in criteria:
        r2_correct = 0
        for f in judged:
            excerpt = f.sample_excerpts[0] if f.sample_excerpts else ""
            v = judge_type_accuracy(excerpt, f.canonical_type,
                                    context=_context_for(f, chunks), model=model, client=client)
            r2_correct += v.correct
            if not v.correct:
                hard_fail = True
                _record(conn, scan_id, "R2_type_accuracy", 0.0, "fail",
                        f"{f.canonical_type}: {v.reason}")
        r2_score = r2_correct / len(judged) if judged else 1.0
        _record(conn, scan_id, "R2_type_accuracy", r2_score,
                "pass" if r2_score == 1.0 else "fail", f"{r2_correct}/{len(judged)} correct")
        ran["R2"] = True

    if "R3" in criteria and source_text:
        detected = [e for f in result.findings for e in f.sample_excerpts]
        v = judge_coverage(source_text[:PASSAGE_CAP], detected, model=model, client=client)
        _record(conn, scan_id, "R3_coverage", 0.0 if v.answer else 1.0,
                "warn" if v.answer else "pass", v.reason)
        ran["R3"] = True

    if "R5" in criteria:
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
        ran["R5"] = True

    if "R6" in criteria and source_text:
        report = ", ".join(f"{f.canonical_type}={e!r}"
                           for f in result.findings for e in f.sample_excerpts) or "(no findings)"
        v = judge_injection_live(source_text[:PASSAGE_CAP], report, model=model, client=client)
        hard_fail |= v.answer
        _record(conn, scan_id, "R6_injection", 0.0 if v.answer else 1.0,
                "fail" if v.answer else "pass", v.reason)
        ran["R6"] = True

    label = "flagged" if hard_fail else "pass"
    _record(conn, scan_id, "overall", 0.0 if hard_fail else 1.0, label,
            f"criteria run: {sorted(ran)}" if hard_fail else "all HARD criteria green")
    return {"scan_id": scan_id, "label": label, "criteria_run": sorted(ran)}


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
