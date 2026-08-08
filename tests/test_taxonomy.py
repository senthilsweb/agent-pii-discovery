"""Taxonomy + alias normalization: both label families, closed type set."""

import pytest

from pipeline.taxonomy import CANONICAL_ENTITY_TYPES, normalize_label


def test_canonical_set_is_36_types():
    assert len(CANONICAL_ENTITY_TYPES) == 36
    assert len(set(CANONICAL_ENTITY_TYPES)) == 36
    assert "UNKNOWN" in CANONICAL_ENTITY_TYPES


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Presidio-native vocabulary
        ("PERSON", "PERSON_NAME"),
        ("US_SSN", "GOVERNMENT_ID_SSN"),
        ("CREDIT_CARD", "CREDIT_CARD_NUMBER"),
        ("IP_ADDRESS", "IP_ADDRESS"),
        ("IBAN_CODE", "IBAN"),
        ("UK_NINO", "GOVERNMENT_ID_NATIONAL"),
        # LLM free-text phrasing (case/space/hyphen-insensitive)
        ("Full Name", "PERSON_NAME"),
        ("e-mail", "EMAIL_ADDRESS"),
        ("Social Security Number", "GOVERNMENT_ID_SSN"),
        ("date of birth", "DATE_OF_BIRTH"),
        # Canonical names resolve to themselves
        ("EMAIL_ADDRESS", "EMAIL_ADDRESS"),
        ("person_name", "PERSON_NAME"),
    ],
)
def test_alias_resolution(raw, expected):
    assert normalize_label(raw) == expected


def test_unrecognized_degrades_to_unknown_never_throws():
    assert normalize_label("flux capacitor reading") == "UNKNOWN"
    assert normalize_label("") == "UNKNOWN"


def test_missing_config_file_falls_back_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("LABEL_ALIASES_FILE", str(tmp_path / "nope.yaml"))
    assert normalize_label("PERSON") == "UNKNOWN"


def test_config_cannot_invent_types(monkeypatch, tmp_path):
    rogue = tmp_path / "rogue.yaml"
    rogue.write_text(
        "version: 1\nfallback: UNKNOWN\ncanonical_types:\n"
        "  TOTALLY_NEW_TYPE:\n    aliases: [surprise]\n"
        "  EMAIL_ADDRESS:\n    aliases: [email]\n"
    )
    monkeypatch.setenv("LABEL_ALIASES_FILE", str(rogue))
    assert normalize_label("surprise") == "UNKNOWN"  # unknown key ignored
    assert normalize_label("email") == "EMAIL_ADDRESS"
