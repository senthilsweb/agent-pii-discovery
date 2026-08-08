"""R1 + R4 — the deterministic judge criteria (100% of traces, no LLM).

R1 Grounding (HARD): every sample excerpt is a whitespace/case-normalized
substring of the source text. R4 Span fidelity (SOFT): recorded spans bound
their excerpt within ±5 chars. Both operate on a persisted DocumentResult
plus the source text, so they run identically offline, in CI, and against
live traces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.schemas import DocumentResult

SPAN_TOLERANCE = 5


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class CheckVerdict:
    """One criterion's outcome over one result."""
    criterion: str
    passed: bool
    failures: list[str] = field(default_factory=list)


def check_grounding(result: DocumentResult, source_text: str) -> CheckVerdict:
    """R1 (HARD): every excerpt must exist verbatim (normalized) in the source."""
    norm_text = _norm(source_text)
    failures = []
    for f in result.findings:
        for excerpt in f.sample_excerpts:
            if _norm(excerpt) not in norm_text:
                failures.append(f"{f.canonical_type}: {excerpt[:60]!r}")
    return CheckVerdict("R1_grounding", not failures, failures)


def check_span_fidelity(result: DocumentResult, chunks: dict[str, str]) -> CheckVerdict:
    """R4 (SOFT): spans bound their excerpt within ±SPAN_TOLERANCE chars.

    `chunks` maps chunk_id → chunk text. Spans citing unknown chunks fail;
    findings without spans are simply not judged here (spans are best-effort
    for the GenAI leg).
    """
    failures = []
    for f in result.findings:
        excerpts = [_norm(e) for e in f.sample_excerpts]
        for span in f.spans:
            text = chunks.get(span.chunk_id)
            if text is None:
                failures.append(f"{f.canonical_type}: unknown chunk {span.chunk_id}")
                continue
            lo = max(0, span.start - SPAN_TOLERANCE)
            hi = min(len(text), span.end + SPAN_TOLERANCE)
            window = _norm(text[lo:hi])
            if not any(e in window for e in excerpts):
                failures.append(f"{f.canonical_type}: span [{span.start},{span.end}) misses excerpt")
    return CheckVerdict("R4_span_fidelity", not failures, failures)
