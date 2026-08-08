"""Canonical entity taxonomy and label normalization.

Port of the monorepo's shared/lib/taxonomy.ts. The invariants that matter:
the canonical type list is closed (config can never invent a type), unknown
labels degrade to the fallback instead of throwing, and one alias table
normalizes both Presidio's native vocabulary and LLM free-text labels.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

CANONICAL_ENTITY_TYPES: tuple[str, ...] = (
    "PERSON_NAME", "EMAIL_ADDRESS", "PHONE_NUMBER", "PHYSICAL_ADDRESS",
    "ZIP_POSTAL_CODE", "GEOLOCATION", "DATE_OF_BIRTH", "GENDER",
    "RACE_ETHNICITY", "RELIGIOUS_BELIEF", "SEXUAL_ORIENTATION",
    "POLITICAL_OPINION", "GOVERNMENT_ID_SSN", "GOVERNMENT_ID_NATIONAL",
    "GOVERNMENT_ID_PASSPORT", "GOVERNMENT_ID_DRIVER_LICENSE",
    "GOVERNMENT_ID_TAX", "FINANCIAL_ACCOUNT_NUMBER", "CREDIT_CARD_NUMBER",
    "BANK_ROUTING_NUMBER", "IBAN", "CRYPTO_WALLET_ADDRESS",
    "HEALTH_CONDITION", "HEALTH_RECORD_ID", "BIOMETRIC_IDENTIFIER",
    "GENETIC_DATA", "IP_ADDRESS", "MAC_ADDRESS", "DEVICE_IDENTIFIER",
    "LOGIN_CREDENTIAL", "EMPLOYMENT_INFO", "EDUCATION_INFO",
    "VEHICLE_IDENTIFIER", "MINOR_DATA", "OTHER_SENSITIVE", "UNKNOWN",
)

_DEFAULT_ALIASES_PATH = Path(__file__).resolve().parent.parent / "config" / "label_aliases.yaml"

_cache: dict | None = None


def _normalize_key(raw: str) -> str:
    """Lowercase and map spaces/hyphens to underscores — the matching rule."""
    return raw.strip().lower().replace(" ", "_").replace("-", "_")


def _load_config() -> dict:
    """Load the alias YAML into {normalized_alias: canonical_type} + fallback.

    Unrecognized canonical keys are ignored; a missing or unparseable file
    yields an empty table (everything falls back) rather than an exception —
    detection must never die on a config typo.
    """
    global _cache
    if _cache is not None:
        return _cache

    path = Path(os.environ.get("LABEL_ALIASES_FILE") or _DEFAULT_ALIASES_PATH)
    table: dict[str, str] = {}
    fallback = "UNKNOWN"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        candidate = str(raw.get("fallback") or "UNKNOWN")
        if candidate in CANONICAL_ENTITY_TYPES:
            fallback = candidate
        for canonical, spec in (raw.get("canonical_types") or {}).items():
            if canonical not in CANONICAL_ENTITY_TYPES:
                continue  # config can never invent a type
            table[_normalize_key(canonical)] = canonical
            for alias in (spec or {}).get("aliases") or []:
                table[_normalize_key(str(alias))] = canonical
    except (OSError, yaml.YAMLError):
        pass

    _cache = {"table": table, "fallback": fallback}
    return _cache


def normalize_label(raw_label: str) -> str:
    """Map an engine/model label to a canonical type, degrading to fallback."""
    cfg = _load_config()
    return cfg["table"].get(_normalize_key(raw_label), cfg["fallback"])


def _reset_cache_for_tests() -> None:
    """Test escape hatch — clears the module-scope config cache."""
    global _cache
    _cache = None
