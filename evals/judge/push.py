"""Judge a freshly-completed scan and push verdicts to Arize (Phase 5).

Runs immediately after the trace forwarder, in the SAME client process,
while the original document is still on disk. This is deliberate: production
spans carry no document text (`TELEMETRY_RECORD_IO=false`), our S3 mirror is
a dev-mode no-op unless a bucket is configured, and the sandbox's extracted
text is ephemeral — so cold-storage re-fetch is not a reliable source. The
one place the text is guaranteed to still exist is the client process that
just drove the scan. See ADR 0002 for the full reasoning.

Cost control (PRD §10.4): R1 (grounding) and R4 (span fidelity) are free
code checks and run on every scan. The four LLM judges (R2/R3/R5/R6) run
only on a sampled subset — default 25%, `PII_JUDGE_SAMPLE_RATE` — chosen
deterministically from the scan_id so a given scan always samples the same
way (reruns don't flip a flagged scan into "not sampled" and back).

Never fails a scan: any error here is caught and logged, matching the
forwarder's degrade-to-warning contract.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from evals.judge.runner import ALL_CRITERIA, judge_scan
from pipeline.extract import ExtractionError, extract_text
from pipeline.schemas import DocumentResult
from pipeline.storage import db

log = logging.getLogger("pii.judge_push")

CODE_CRITERIA = frozenset({"R1", "R4"})
LLM_CRITERIA = ALL_CRITERIA - CODE_CRITERIA
DEFAULT_SAMPLE_RATE = 0.25


def resolve_sample_rate() -> float:
    """PII_JUDGE_SAMPLE_RATE, default 0.25, clamped to [0, 1]."""
    raw = os.environ.get("PII_JUDGE_SAMPLE_RATE", "").strip()
    if not raw:
        return DEFAULT_SAMPLE_RATE
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_SAMPLE_RATE


def should_sample(scan_id: str, rate: float) -> bool:
    """Deterministic sampling from scan_id — stable across reruns, testable."""
    digest = hashlib.sha256(scan_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF  # 0.0–1.0, uniform
    return bucket < rate


def _rows_from_eval_scores(conn, scan_id: str, criteria_run: set[str]) -> dict:
    """Pull this scan's just-written eval_scores into one wide dict for Arize:
    {"eval.R1_grounding.label": ..., "eval.R1_grounding.score": ..., ...}."""
    row_map = {}
    for evaluator, score, label, explanation in conn.execute(
        "SELECT evaluator, score, label, explanation FROM eval_scores WHERE scan_id = ?",
        [scan_id],
    ).fetchall():
        prefix = f"eval.{evaluator}"
        row_map[f"{prefix}.label"] = label
        row_map[f"{prefix}.score"] = score
        row_map[f"{prefix}.explanation"] = explanation
    return row_map


def push_to_arize(conn, scan_id: str, root_span_id: str, row_map: dict) -> bool:
    """Build the one-row wide dataframe and call update_evaluations().

    Env-gated: without ARIZE_SPACE_ID/ARIZE_API_KEY this logs one warning and
    returns False. Lazy-imports `arize` and `pandas` so neither is required
    for scans that don't push (e.g. tests, or when telemetry is unconfigured).
    """
    space_id, api_key = os.environ.get("ARIZE_SPACE_ID"), os.environ.get("ARIZE_API_KEY")
    if not (space_id and api_key):
        log.warning("judge_push: ARIZE_SPACE_ID/ARIZE_API_KEY not configured — "
                    "verdicts stayed local in eval_scores only")
        return False
    try:
        import pandas as pd
        from arize import ArizeClient
    except ImportError as exc:
        log.warning("judge_push: %s (install the [evaluate] extra)", exc)
        return False

    df = pd.DataFrame([{"context.span_id": root_span_id, **row_map}])
    client = ArizeClient(api_key=api_key)
    client.spans.update_evaluations(
        space_id=space_id, project_name=os.environ.get("ARIZE_PROJECT_NAME", "agent-pii-discovery"),
        dataframe=df,
    )
    return True


def judge_and_push(result: DocumentResult, source_path: str | Path,
                   root_span_id: str | None, conn,
                   model: str | None = None, client=None,
                   sample_rate: float | None = None) -> dict:
    """Judge one scan and push its verdicts to Arize. The main entrypoint.

    Only `processed` scans are judged (rejects/failures have no findings to
    score). Returns a summary dict; never raises.
    """
    summary = {"scan_id": result.run.scan_id, "judged": False, "pushed": False,
              "criteria_run": [], "sampled": False}
    if result.document.processing_status != "processed":
        summary["reason"] = f"status={result.document.processing_status}, nothing to judge"
        return summary

    rate = resolve_sample_rate() if sample_rate is None else sample_rate
    sampled = should_sample(result.run.scan_id, rate)
    criteria = ALL_CRITERIA if sampled else CODE_CRITERIA
    summary["sampled"] = sampled

    try:
        extraction = extract_text(source_path)
        source_text = extraction.text
    except (ExtractionError, OSError) as exc:
        # Any extraction failure — missing file, unreadable format, OCR
        # miss — degrades to code-checks-only judging rather than crashing
        # the scan. An empty source_text makes R1/R4 fail loudly (nothing
        # can ground against ""), which is the honest outcome: we couldn't
        # verify grounding, so don't claim it passed.
        log.warning("judge_push: could not re-extract %s for judging: %s", source_path, exc)
        source_text = ""

    try:
        verdict = judge_scan(conn, result, source_text, model=model, client=client,
                             criteria=criteria)
        summary["judged"] = True
        summary["label"] = verdict["label"]
        summary["criteria_run"] = verdict["criteria_run"]
        db.mark_judged(conn, result.run.scan_id)
    except Exception as exc:  # noqa: BLE001 — never fail a scan on judge error
        log.warning("judge_push: judging failed for %s: %s", result.run.scan_id, exc)
        return summary

    if root_span_id:
        row_map = _rows_from_eval_scores(conn, result.run.scan_id, set(verdict["criteria_run"]))
        try:
            summary["pushed"] = push_to_arize(conn, result.run.scan_id, root_span_id, row_map)
        except Exception as exc:  # noqa: BLE001 — telemetry never fails a scan
            log.warning("judge_push: Arize push failed for %s: %s", result.run.scan_id, exc)
    else:
        log.warning("judge_push: no root_span_id for %s — verdicts stayed local", result.run.scan_id)

    return summary
