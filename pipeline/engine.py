"""PII_ENGINE resolution — required, no silent default, fail fast on reserved.

Port of the monorepo's engine switch. `openai_privacy_filter` was evaluated
and ruled out of scope (PRD §15); naming it fails with the reason rather than
pretending it might work.
"""

from __future__ import annotations

import os

VALID_ENGINES = ("presidio", "presidio_genai", "genai_only")
_OUT_OF_SCOPE = {
    "openai_privacy_filter": (
        "ruled out of scope 2026-08-07 — its 8-class taxonomy cannot express "
        "the 36 canonical types (PRD §15)"
    ),
}


def resolve_pii_engine() -> str:
    """Read PII_ENGINE or die loudly — an unset engine is a config bug."""
    value = os.environ.get("PII_ENGINE", "").strip()
    if not value:
        raise RuntimeError(f"PII_ENGINE is required; set one of {VALID_ENGINES}")
    if value in _OUT_OF_SCOPE:
        raise RuntimeError(f"PII_ENGINE={value}: {_OUT_OF_SCOPE[value]}")
    if value not in VALID_ENGINES:
        raise RuntimeError(f"PII_ENGINE={value!r} is not one of {VALID_ENGINES}")
    return value


def uses_presidio(engine: str) -> bool:
    """Does this engine run the deterministic Presidio path?"""
    return engine in ("presidio", "presidio_genai")


def uses_genai(engine: str) -> bool:
    """Does this engine run the generative extraction path?"""
    return engine in ("presidio_genai", "genai_only")
