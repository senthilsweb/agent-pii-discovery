"""The normalizer — pure lookup and union, no LLM anywhere.

Port of the monorepo's normalize_findings.ts: raw findings from every engine
and model roll up per canonical type; sensitivity takes the max via rank;
excerpts cap at 5; output sorts by canonical type. Optionally computes a
canonical `normalized_value` for types with an obvious canonical form.
"""

from __future__ import annotations

import re

from pipeline.schemas import SENSITIVITY_RANK, NormalizedFinding, RawFinding
from pipeline.taxonomy import normalize_label

_MAX_EXCERPTS = 5
_MAX_SPANS = 20


def _normalized_value(canonical_type: str, excerpts: list[str]) -> str | None:
    """Canonical form where one is computable; None otherwise."""
    if not excerpts:
        return None
    first = excerpts[0].strip()
    if canonical_type == "EMAIL_ADDRESS":
        return first.lower()
    if canonical_type == "PHONE_NUMBER":
        digits = re.sub(r"[^\d+]", "", first)
        return digits or None
    return None


def normalize_findings(raw: list[RawFinding]) -> list[NormalizedFinding]:
    """Group raw findings by canonical type and roll them up."""
    groups: dict[str, list[RawFinding]] = {}
    for f in raw:
        groups.setdefault(normalize_label(f.raw_label), []).append(f)

    out: list[NormalizedFinding] = []
    for canonical, items in groups.items():
        excerpts: list[str] = []
        for f in items:
            if f.value_excerpt not in excerpts:
                excerpts.append(f.value_excerpt)
        sensitivity = max((f.sensitivity for f in items), key=lambda s: SENSITIVITY_RANK[s])
        out.append(
            NormalizedFinding(
                canonical_type=canonical,
                raw_labels_seen=sorted({f.raw_label for f in items}),
                occurrences=len(items),
                chunk_ids=sorted({f.chunk_id for f in items}),
                sample_excerpts=excerpts[:_MAX_EXCERPTS],
                spans=[f.span for f in items if f.span is not None][:_MAX_SPANS],
                normalized_value=_normalized_value(canonical, excerpts),
                max_confidence=max(f.confidence for f in items),
                sensitivity=sensitivity,
                source_engines=sorted({f.source_engine for f in items}),
                source_models=sorted({f.source_model for f in items if f.source_model}),
            )
        )
    out.sort(key=lambda n: n.canonical_type)
    return out
