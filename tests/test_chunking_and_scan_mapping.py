"""Chunk offset math and the Presidio hit → RawFinding mapping."""

from pipeline.chunking import chunk_text, locate_chunk
from pipeline.presidio_scan import scan_with


def test_chunk_offsets_reconstruct_source():
    text = "Para one.\n\nPara two is here.\n\nPara three ends it."
    chunks = chunk_text(text)
    assert [c.chunk_id for c in chunks] == [f"chunk_{i:04d}" for i in range(1, len(chunks) + 1)]
    for c in chunks:
        assert text[c.doc_start : c.doc_start + len(c.text)] == c.text


def test_chunking_is_deterministic_and_respects_max():
    text = "\n\n".join(f"Paragraph number {i} " + "x" * 80 for i in range(30))
    a = chunk_text(text, max_chars=500)
    b = chunk_text(text, max_chars=500)
    assert [(c.chunk_id, c.doc_start) for c in a] == [(c.chunk_id, c.doc_start) for c in b]
    assert all(len(c.text) <= 500 for c in a)


def test_locate_chunk_finds_the_right_one():
    text = "First block.\n\nSecond block."
    chunks = chunk_text(text)
    idx = text.index("Second")
    assert locate_chunk(chunks, idx).chunk_id == chunks[-1].chunk_id
    assert locate_chunk(chunks, 10_000) is None


def test_scan_with_maps_hits_to_chunk_relative_spans(fake_analyzer_factory):
    text = "Contact Priya Raman today.\n\nHer email is priya@example.com for now."
    chunks = chunk_text(text)
    analyzer = fake_analyzer_factory(text, [
        ("PERSON", "Priya Raman"),
        ("EMAIL_ADDRESS", "priya@example.com"),
    ])
    findings = scan_with(analyzer, text, chunks)
    assert len(findings) == 2
    for f in findings:
        chunk = next(c for c in chunks if c.chunk_id == f.chunk_id)
        assert chunk.text[f.span.start : f.span.end] == f.value_excerpt  # grounding
    assert findings[0].source_engine == "presidio"
    assert findings[1].raw_label == "EMAIL_ADDRESS"
