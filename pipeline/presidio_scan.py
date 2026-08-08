"""The deterministic Presidio path.

Presidio runs once over the full extracted text (matching the monorepo's
routing) and its hits are mapped into chunk-relative RawFindings. The
analyzer is injected so unit tests exercise the mapping with a fake — the
real engine (spaCy model download) is an integration concern, never L1.
"""

from __future__ import annotations

from typing import Any, Protocol

from pipeline.chunking import Chunk, locate_chunk
from pipeline.schemas import RawFinding, Span


class _AnalyzerLike(Protocol):
    def analyze(self, text: str, language: str) -> list[Any]: ...


def get_analyzer() -> _AnalyzerLike:
    """Build the real Presidio engine (requires the [presidio] extra).

    Uses the small spaCy model (en_core_web_sm, ~12 MB) rather than Presidio's
    default en_core_web_lg (~560 MB) so the per-session sandbox bootstrap
    stays fast; the accuracy delta is measured, not assumed — it shows up in
    the L2/L3 per-engine scores, which is exactly where we want to see it.
    """
    from presidio_analyzer import AnalyzerEngine  # lazy import
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])


def scan_with(analyzer: _AnalyzerLike, text: str, chunks: list[Chunk]) -> list[RawFinding]:
    """Run one whole-document analysis and map hits to chunk-relative spans.

    Presidio results carry `entity_type`, `start`, `end`, `score` on the
    document string; hits that fall outside every chunk (separator noise) are
    dropped rather than guessed into a neighbor.
    """
    findings: list[RawFinding] = []
    for hit in analyzer.analyze(text=text, language="en"):
        chunk = locate_chunk(chunks, hit.start)
        if chunk is None:
            continue
        rel_start = hit.start - chunk.doc_start
        rel_end = min(hit.end - chunk.doc_start, len(chunk.text))
        findings.append(
            RawFinding(
                raw_label=hit.entity_type,
                value_excerpt=text[hit.start:hit.end][:200],
                span=Span(chunk_id=chunk.chunk_id, start=rel_start, end=rel_end),
                confidence=max(0.0, min(1.0, float(hit.score))),
                sensitivity="medium",  # Presidio carries no sensitivity; graded downstream
                source_engine="presidio",
                chunk_id=chunk.chunk_id,
            )
        )
    return findings
