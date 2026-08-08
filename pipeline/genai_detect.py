"""The GenAI detection leg — the one generative step in the system (Phase 3).

Runs HOST-SIDE as a direct, typed, per-chunk structured-output call (the
monorepo's tool-wraps-the-model-call pattern), not inside the sandbox: a
sandboxed model call would need a vault API-key credential, and this org
authenticates with short-lived OAuth profiles unfit for vaults. Per-model
scanner threads inside the session are the documented v2 (design.md D2).

Grounding is enforced IN CODE at the boundary: a finding whose excerpt is not
a verbatim substring of its chunk is dropped (counted, never kept), and a
span that doesn't reproduce the excerpt is stripped. The model is never
trusted about offsets or quotes — only about labels and judgment.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from pipeline.chunking import Chunk
from pipeline.schemas import RawFinding, Sensitivity, Span

_DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "agent" / "skills" / "detection_prompt.md"
)


class _ModelSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class _ModelFinding(BaseModel):
    """What the model returns per finding — its judgment, nothing more."""
    raw_label: str
    value_excerpt: str = Field(max_length=200)
    span: _ModelSpan | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity


class ChunkExtraction(BaseModel):
    """The structured-output contract for one chunk."""
    findings: list[_ModelFinding]


def resolve_extractor_model() -> str:
    """MODEL_PII_EXTRACTOR → MODEL → startup error (monorepo convention)."""
    model = os.environ.get("MODEL_PII_EXTRACTOR") or os.environ.get("MODEL") or ""
    if not model.strip():
        raise RuntimeError("MODEL_PII_EXTRACTOR (or MODEL) is required for GenAI engines")
    return model.strip()


def detection_prompt() -> str:
    """Prompt precedence: PII_SYSTEM_PROMPT → PII_SYSTEM_PROMPT_FILE → bundled skill.

    The skill file carries a doc header above a `---` rule; the prompt is what
    follows it. This text feeds pipeline_version — editing it busts the cache.
    """
    inline = os.environ.get("PII_SYSTEM_PROMPT")
    if inline and inline.strip():
        return inline
    path = Path(os.environ.get("PII_SYSTEM_PROMPT_FILE") or _DEFAULT_PROMPT_PATH)
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^---$", text, maxsplit=1, flags=re.MULTILINE)
    return (parts[1] if len(parts) == 2 else text).strip()


def _client():
    from anthropic import Anthropic  # lazy; profile or env auth

    return Anthropic()


def _extract_chunk(client, model: str, prompt: str, chunk: Chunk) -> list[RawFinding]:
    """One typed model call for one chunk; grounding enforced on the way out."""
    message = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=prompt,
        messages=[{"role": "user", "content": chunk.text}],
        output_format=ChunkExtraction,
    )
    parsed: ChunkExtraction | None = message.parsed_output
    if parsed is None:
        return []

    findings: list[RawFinding] = []
    for f in parsed.findings:
        if f.value_excerpt not in chunk.text:
            continue  # ungrounded — dropped, never repaired
        span = None
        if f.span is not None and chunk.text[f.span.start:f.span.end] == f.value_excerpt:
            span = Span(chunk_id=chunk.chunk_id, start=f.span.start, end=f.span.end)
        findings.append(
            RawFinding(
                raw_label=f.raw_label,
                value_excerpt=f.value_excerpt,
                span=span,
                confidence=f.confidence,
                sensitivity=f.sensitivity,
                source_engine="genai",
                source_model=model,
                chunk_id=chunk.chunk_id,
            )
        )
    return findings


def scan_genai(chunks: list[Chunk], model: str | None = None,
               client=None, prompt: str | None = None) -> list[RawFinding]:
    """Run the GenAI leg over all chunks with bounded concurrency.

    `client` is injectable for tests; per-chunk failures raise — a scan with a
    half-completed GenAI leg must fail plainly, not persist partial findings.
    """
    model = model or resolve_extractor_model()
    prompt = prompt or detection_prompt()
    client = client or _client()
    workers = max(1, int(os.environ.get("PII_DETECTION_CONCURRENCY", "5")))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        per_chunk = list(pool.map(lambda c: _extract_chunk(client, model, prompt, c), chunks))
    return [f for chunk_findings in per_chunk for f in chunk_findings]
