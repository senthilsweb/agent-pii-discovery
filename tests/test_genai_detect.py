"""GenAI leg: prompt resolution, model resolution, code-enforced grounding."""

import pytest

from pipeline.chunking import Chunk
from pipeline.genai_detect import (
    ChunkExtraction, _ModelFinding, _ModelSpan,
    detection_prompt, resolve_extractor_model, scan_genai,
)


class _FakeMessage:
    def __init__(self, parsed):
        self.parsed_output = parsed


class FakeGenaiClient:
    """Duck-typed Anthropic client returning a canned ChunkExtraction."""

    def __init__(self, extraction: ChunkExtraction):
        self._extraction = extraction
        outer = self

        class _Messages:
            def parse(self, **kwargs):
                outer.last_kwargs = kwargs
                return _FakeMessage(outer._extraction)

        self.messages = _Messages()


CHUNK = Chunk(chunk_id="chunk_0001",
              text="Reach Priya at priya@example.com or call 555-0104 today.",
              doc_start=0)


def _finding(excerpt, label="email", span=None, conf=0.9):
    return _ModelFinding(raw_label=label, value_excerpt=excerpt, span=span,
                         confidence=conf, sensitivity="medium")


def test_grounded_findings_pass_with_source_model():
    client = FakeGenaiClient(ChunkExtraction(findings=[
        _finding("priya@example.com", span=_ModelSpan(start=15, end=32)),
    ]))
    out = scan_genai([CHUNK], model="claude-haiku-4-5", client=client, prompt="p")
    assert len(out) == 1
    f = out[0]
    assert f.source_engine == "genai" and f.source_model == "claude-haiku-4-5"
    assert f.span is not None and CHUNK.text[f.span.start:f.span.end] == f.value_excerpt


def test_ungrounded_finding_dropped():
    client = FakeGenaiClient(ChunkExtraction(findings=[
        _finding("fabricated@nowhere.example"),  # not in the chunk
        _finding("priya@example.com"),
    ]))
    out = scan_genai([CHUNK], model="m", client=client, prompt="p")
    assert [f.value_excerpt for f in out] == ["priya@example.com"]


def test_bad_span_stripped_but_finding_kept():
    client = FakeGenaiClient(ChunkExtraction(findings=[
        _finding("priya@example.com", span=_ModelSpan(start=0, end=5)),  # wrong offsets
    ]))
    (f,) = scan_genai([CHUNK], model="m", client=client, prompt="p")
    assert f.span is None and f.value_excerpt == "priya@example.com"


def test_prompt_resolution_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("PII_SYSTEM_PROMPT", "inline wins")
    assert detection_prompt() == "inline wins"
    monkeypatch.delenv("PII_SYSTEM_PROMPT")
    custom = tmp_path / "p.md"
    custom.write_text("header\n---\nthe real prompt")
    monkeypatch.setenv("PII_SYSTEM_PROMPT_FILE", str(custom))
    assert detection_prompt() == "the real prompt"
    monkeypatch.delenv("PII_SYSTEM_PROMPT_FILE")
    bundled = detection_prompt()  # the skill file: header stripped at the --- rule
    assert "PII detection engine" in bundled and "# Skill" not in bundled


def test_model_resolution_chain(monkeypatch):
    monkeypatch.setenv("MODEL_PII_EXTRACTOR", "claude-sonnet-5")
    assert resolve_extractor_model() == "claude-sonnet-5"
    monkeypatch.delenv("MODEL_PII_EXTRACTOR")
    monkeypatch.setenv("MODEL", "fallback-model")
    assert resolve_extractor_model() == "fallback-model"
    monkeypatch.delenv("MODEL")
    with pytest.raises(RuntimeError):
        resolve_extractor_model()
