"""Compliance-impact mapping — pure YAML lookup, never a model verdict.

Port of the monorepo's compliance.ts against config/compliance_matrix.yaml.
Severity derives from a fixed high-severity type set; everything else that
triggers a regime is `moderate`. Missing/unparseable config degrades to an
empty matrix (no hits) rather than crashing a scan.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from pipeline.schemas import ComplianceHit, ComplianceImpact
from pipeline.taxonomy import CANONICAL_ENTITY_TYPES

_DEFAULT_MATRIX_PATH = Path(__file__).resolve().parent.parent / "config" / "compliance_matrix.yaml"

HIGH_SEVERITY_TYPES = {
    "GOVERNMENT_ID_SSN", "GOVERNMENT_ID_NATIONAL", "GOVERNMENT_ID_PASSPORT",
    "GOVERNMENT_ID_DRIVER_LICENSE", "GOVERNMENT_ID_TAX",
    "HEALTH_CONDITION", "HEALTH_RECORD_ID", "BIOMETRIC_IDENTIFIER",
    "GENETIC_DATA", "RACE_ETHNICITY", "RELIGIOUS_BELIEF",
    "SEXUAL_ORIENTATION", "POLITICAL_OPINION",
    "FINANCIAL_ACCOUNT_NUMBER", "CREDIT_CARD_NUMBER", "MINOR_DATA",
}

_cache: dict | None = None


def _load_matrix() -> dict:
    """Load {version, jurisdictions, mappings, default}, ignoring unknown types."""
    global _cache
    if _cache is not None:
        return _cache
    path = Path(os.environ.get("COMPLIANCE_MATRIX_FILE") or _DEFAULT_MATRIX_PATH)
    version, jurisdictions, mappings, default = "0", {}, {}, []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        version = str(raw.get("version") or "0")
        jurisdictions = raw.get("jurisdictions") or {}
        default = [j for j in (raw.get("default") or []) if j in jurisdictions]
        for ctype, regimes in (raw.get("mappings") or {}).items():
            if ctype in CANONICAL_ENTITY_TYPES:
                mappings[ctype] = [j for j in (regimes or []) if j in jurisdictions]
    except (OSError, yaml.YAMLError):
        pass
    _cache = {"version": version, "jurisdictions": jurisdictions,
              "mappings": mappings, "default": default}
    return _cache


def map_compliance_impact(canonical_types: list[str]) -> ComplianceImpact:
    """Which regimes the detected types implicate, and how severely."""
    m = _load_matrix()
    triggered: dict[str, list[str]] = {}
    for ctype in canonical_types:
        for jur in m["mappings"].get(ctype, m["default"]):
            triggered.setdefault(jur, [])
            if ctype not in triggered[jur]:
                triggered[jur].append(ctype)

    hits = []
    for jur in sorted(triggered):
        types = sorted(triggered[jur])
        severity = "high" if any(t in HIGH_SEVERITY_TYPES for t in types) else "moderate"
        hits.append(
            ComplianceHit(
                jurisdiction=jur,
                regulation_name=str(m["jurisdictions"][jur].get("regulation_name", jur)),
                triggered_by=types,
                severity=severity,
            )
        )
    return ComplianceImpact(
        impacted_jurisdictions=[h.jurisdiction for h in hits],
        hits=hits,
        regime_matrix_version=m["version"],
    )


def _reset_cache_for_tests() -> None:
    """Test escape hatch — clears the module-scope matrix cache."""
    global _cache
    _cache = None
