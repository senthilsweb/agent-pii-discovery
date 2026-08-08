"""Deterministic paragraph chunking with stable ids and document offsets.

Chunk ids are stable (`chunk_0001`, ...) because findings cite them — the
corpus labels and the grounding evals both depend on a chunk's text and its
absolute position in the document never moving between runs.
"""

from __future__ import annotations

from dataclasses import dataclass

_MAX_CHUNK_CHARS = 2000


@dataclass
class Chunk:
    """One chunk and where it sits in the source document."""
    chunk_id: str
    text: str
    doc_start: int  # absolute char offset of text[0] in the document


def chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[Chunk]:
    """Split on blank lines, packing paragraphs up to max_chars per chunk.

    Offsets are tracked against the original string (including the blank-line
    separators), so `text[c.doc_start : c.doc_start + len(c.text)] == c.text`
    holds for every chunk — the property the span math relies on.
    """
    chunks: list[Chunk] = []
    n = len(text)
    pos = 0
    current_start: int | None = None
    current_end = 0

    def flush() -> None:
        nonlocal current_start
        if current_start is not None and text[current_start:current_end].strip():
            chunks.append(
                Chunk(
                    chunk_id=f"chunk_{len(chunks) + 1:04d}",
                    text=text[current_start:current_end],
                    doc_start=current_start,
                )
            )
        current_start = None

    while pos < n:
        # locate next paragraph [para_start, para_end)
        para_end = text.find("\n\n", pos)
        if para_end == -1:
            para_end = n
        para_start = pos
        if current_start is None:
            current_start = para_start
            current_end = para_end
        elif (para_end - current_start) <= max_chars:
            current_end = para_end
        else:
            flush()
            current_start = para_start
            current_end = para_end
        pos = para_end + 2  # skip the separator
    flush()
    return chunks


def locate_chunk(chunks: list[Chunk], doc_offset: int) -> Chunk | None:
    """Find the chunk containing an absolute document offset."""
    for c in chunks:
        if c.doc_start <= doc_offset < c.doc_start + len(c.text):
            return c
    return None
