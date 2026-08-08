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
    """Build the real Presidio engine (requires the [presidio] extra)."""
    from presidio_analyzer import AnalyzerEngine  # lazy import

    return AnalyzerEngine()


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
