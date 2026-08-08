#!/usr/bin/env python3
"""Corpus integrity verifier for the synthetic PII fixture corpus.

Pure Python stdlib. Re-reads every fixture under evals/data/ and asserts the
contract from evals/rubrics.md §1 and the corpus spec:

  - every non-null span satisfies text[start:end] == value EXACTLY
    (spans were recorded at composition time by generate.py; this check
    proves they survived serialization untouched);
  - injected_instruction spans (injection group) satisfy the same rule;
  - every fixture id is unique and matches its directory name;
  - per-group fixture counts match the spec;
  - all 35 plantable canonical types are covered across synthetic_prose
    fixtures (UNKNOWN is a normalizer fallback, never planted);
  - Tier-1 types appear in at least 4 prose fixtures each, and each Tier-1
    type has at least one prose fixture containing the same value twice;
  - OCR fixtures have null spans and their values appear verbatim in the
    source prose fixture named in `notes`;
  - columnar fixtures have empty entities and expect=skipped_out_of_scope;
  - clean fixtures have empty entities and expect=processed.

Run:  python3 verify.py     (exit 0 and a coverage table when green)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
DATA_DIR = CORPUS_DIR.parent / "data"

CANONICAL_ENTITY_TYPES = [
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
]

# UNKNOWN is a normalizer fallback — never planted as a label.
PLANTABLE_TYPES = [t for t in CANONICAL_ENTITY_TYPES if t != "UNKNOWN"]

TIER1_TYPES = [
    "EMAIL_ADDRESS", "PHONE_NUMBER", "GOVERNMENT_ID_SSN",
    "CREDIT_CARD_NUMBER", "IP_ADDRESS",
]

EXPECTED_GROUP_COUNTS = {
    "synthetic_prose": 12,
    "synthetic_ocr": 3,
    "columnar": 2,
    "clean": 4,
    "injection": 4,
    "idiom": 4,
}

DOCUMENT_FILE_BY_GROUP = {
    "synthetic_prose": "document.txt",
    "synthetic_ocr": "document.png",
    "columnar": "document.csv",
    "clean": "document.txt",
    "injection": "document.txt",
    "idiom": "document.txt",
}


def load_fixtures() -> list[dict]:
    """Load every fixture as {id, dir, labels, text|None}."""
    if not DATA_DIR.is_dir():
        raise AssertionError(f"missing corpus data directory: {DATA_DIR}")
    fixtures = []
    for fixture_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        labels_path = fixture_dir / "labels.json"
        assert labels_path.is_file(), f"{fixture_dir.name}: missing labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        group = labels.get("group")
        assert group in EXPECTED_GROUP_COUNTS, (
            f"{fixture_dir.name}: unexpected group {group!r}"
        )
        doc_name = DOCUMENT_FILE_BY_GROUP[group]
        doc_path = fixture_dir / doc_name
        assert doc_path.is_file(), f"{fixture_dir.name}: missing {doc_name}"
        text = None
        if doc_name != "document.png":
            text = doc_path.read_text(encoding="utf-8")
        fixtures.append(
            {"id": fixture_dir.name, "dir": fixture_dir, "labels": labels, "text": text}
        )
    return fixtures


def check_ids(fixtures: list[dict]) -> None:
    seen: set[str] = set()
    for f in fixtures:
        fid = f["labels"].get("fixture_id")
        assert fid == f["id"], (
            f"{f['id']}: fixture_id {fid!r} does not match directory name"
        )
        assert fid not in seen, f"duplicate fixture_id {fid!r}"
        seen.add(fid)
        assert f["labels"].get("created_at") == "2026-08-07", (
            f"{fid}: unexpected created_at"
        )
        assert f["labels"].get("generator_version") == "1", (
            f"{fid}: unexpected generator_version"
        )


def check_group_counts(fixtures: list[dict]) -> None:
    counts = Counter(f["labels"]["group"] for f in fixtures)
    assert dict(counts) == EXPECTED_GROUP_COUNTS, (
        f"group counts {dict(counts)} != expected {EXPECTED_GROUP_COUNTS}"
    )


def check_spans(fixtures: list[dict]) -> None:
    for f in fixtures:
        fid, labels, text = f["id"], f["labels"], f["text"]
        group = labels["group"]
        for ent in labels["entities"]:
            ctype = ent["canonical_type"]
            assert ctype in PLANTABLE_TYPES, (
                f"{fid}: non-plantable or unknown canonical_type {ctype!r}"
            )
            if group == "synthetic_ocr":
                assert ent["start"] is None and ent["end"] is None, (
                    f"{fid}: OCR fixture entities must have null spans"
                )
                continue
            start, end = ent["start"], ent["end"]
            assert isinstance(start, int) and isinstance(end, int) and start < end, (
                f"{fid}: bad span ({start!r}, {end!r})"
            )
            assert text is not None
            assert text[start:end] == ent["value"], (
                f"{fid}: span mismatch for {ctype}: "
                f"text[{start}:{end}]={text[start:end]!r} != {ent['value']!r}"
            )
        inj = labels.get("injected_instruction")
        if group == "injection":
            assert inj is not None, f"{fid}: injection fixture missing injected_instruction"
            assert text is not None
            assert text[inj["start"]:inj["end"]] == inj["value"], (
                f"{fid}: injected_instruction span mismatch"
            )
        else:
            assert inj is None, f"{fid}: unexpected injected_instruction in group {group}"


def check_expectations(fixtures: list[dict]) -> None:
    for f in fixtures:
        fid, labels = f["id"], f["labels"]
        group, expect = labels["group"], labels["expect"]
        if group == "columnar":
            assert expect == "skipped_out_of_scope", f"{fid}: columnar must be skipped"
            assert labels["entities"] == [], f"{fid}: columnar entities must be empty"
        else:
            assert expect == "processed", f"{fid}: expect must be 'processed'"
        if group == "clean":
            assert labels["entities"] == [], f"{fid}: clean fixture must have no entities"
        if group in ("synthetic_prose", "synthetic_ocr", "injection", "idiom"):
            assert labels["entities"], f"{fid}: {group} fixture must have entities"


def check_ocr_sources(fixtures: list[dict]) -> None:
    by_id = {f["id"]: f for f in fixtures}
    for f in fixtures:
        if f["labels"]["group"] != "synthetic_ocr":
            continue
        fid, notes = f["id"], f["labels"]["notes"]
        m = re.search(r"source_fixture=(\S+?)\.", notes)
        assert m, f"{fid}: notes must name source_fixture=<id>"
        source = by_id.get(m.group(1))
        assert source is not None, f"{fid}: unknown source fixture {m.group(1)!r}"
        src_text = source["text"]
        for ent in f["labels"]["entities"]:
            assert ent["value"] in src_text, (
                f"{fid}: OCR value {ent['value']!r} not found in source "
                f"{source['id']} text"
            )


def prose_type_stats(fixtures: list[dict]) -> tuple[Counter, dict[str, set[str]]]:
    """(occurrence count per type, fixture-id set per type) over prose group."""
    occurrences: Counter = Counter()
    fixture_sets: dict[str, set[str]] = defaultdict(set)
    for f in fixtures:
        if f["labels"]["group"] != "synthetic_prose":
            continue
        for ent in f["labels"]["entities"]:
            occurrences[ent["canonical_type"]] += 1
            fixture_sets[ent["canonical_type"]].add(f["id"])
    return occurrences, fixture_sets


def check_coverage(fixtures: list[dict]) -> None:
    occurrences, fixture_sets = prose_type_stats(fixtures)
    missing = [t for t in PLANTABLE_TYPES if occurrences[t] == 0]
    assert not missing, f"types never planted in synthetic_prose: {missing}"
    for t in TIER1_TYPES:
        n = len(fixture_sets[t])
        assert n >= 4, f"Tier-1 type {t} appears in only {n} prose fixtures (< 4)"
        # At least one prose fixture repeats the same value for this type.
        has_dup = False
        for f in fixtures:
            if f["labels"]["group"] != "synthetic_prose":
                continue
            vals = [
                e["value"] for e in f["labels"]["entities"]
                if e["canonical_type"] == t
            ]
            if len(vals) != len(set(vals)):
                has_dup = True
                break
        assert has_dup, (
            f"Tier-1 type {t}: no prose fixture repeats the same value twice"
        )


def coverage_table(fixtures: list[dict]) -> str:
    occurrences, fixture_sets = prose_type_stats(fixtures)
    lines = [
        f"{'canonical_type':<30} {'occurrences':>11} {'fixtures':>8}",
        "-" * 51,
    ]
    for t in PLANTABLE_TYPES:
        lines.append(f"{t:<30} {occurrences[t]:>11} {len(fixture_sets[t]):>8}")
    lines.append("-" * 51)
    lines.append(
        f"{'TOTAL (synthetic_prose)':<30} {sum(occurrences.values()):>11} "
        f"{len({fid for s in fixture_sets.values() for fid in s}):>8}"
    )
    return "\n".join(lines)


def run_all() -> list[dict]:
    fixtures = load_fixtures()
    check_ids(fixtures)
    check_group_counts(fixtures)
    check_spans(fixtures)
    check_expectations(fixtures)
    check_ocr_sources(fixtures)
    check_coverage(fixtures)
    return fixtures


def main() -> int:
    try:
        fixtures = run_all()
    except AssertionError as exc:
        print(f"CORPUS INTEGRITY FAIL: {exc}", file=sys.stderr)
        return 1
    counts = Counter(f["labels"]["group"] for f in fixtures)
    print(f"Corpus OK: {len(fixtures)} fixtures")
    for group in EXPECTED_GROUP_COUNTS:
        print(f"  {group:<16} {counts[group]}")
    print()
    print("Coverage over synthetic_prose (type -> occurrences -> fixtures):")
    print(coverage_table(fixtures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
