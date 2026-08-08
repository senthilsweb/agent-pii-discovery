"""Normalizer roll-up rules: grouping, unions, max sensitivity, caps, sort."""

from pipeline.normalize import normalize_findings
from pipeline.schemas import RawFinding, Span


def raw(label, excerpt, chunk="chunk_0001", conf=0.8, sens="medium",
        engine="presidio", model=None):
    return RawFinding(
        raw_label=label, value_excerpt=excerpt,
        span=Span(chunk_id=chunk, start=0, end=len(excerpt)),
        confidence=conf, sensitivity=sens, source_engine=engine,
        source_model=model, chunk_id=chunk,
    )


def test_groups_across_engines_and_models():
    findings = normalize_findings([
        raw("PERSON", "Priya Raman"),
        raw("full name", "Priya Raman", chunk="chunk_0002", engine="genai", model="claude-opus-5"),
        raw("EMAIL_ADDRESS", "a@example.com"),
    ])
    types = [f.canonical_type for f in findings]
    assert types == sorted(types)  # sorted output
    person = next(f for f in findings if f.canonical_type == "PERSON_NAME")
    assert person.occurrences == 2
    assert person.chunk_ids == ["chunk_0001", "chunk_0002"]
    assert person.source_engines == ["genai", "presidio"]
    assert person.source_models == ["claude-opus-5"]
    assert set(person.raw_labels_seen) == {"PERSON", "full name"}


def test_max_sensitivity_and_confidence():
    findings = normalize_findings([
        raw("ssn", "900-11-0001", sens="medium", conf=0.6),
        raw("US_SSN", "900-11-0001", sens="critical", conf=0.9),
    ])
    (f,) = findings
    assert f.sensitivity == "critical"
    assert f.max_confidence == 0.9


def test_excerpt_cap_at_five_distinct():
    items = [raw("email", f"user{i}@example.com") for i in range(8)]
    (f,) = normalize_findings(items)
    assert len(f.sample_excerpts) == 5
    assert f.occurrences == 8


def test_normalized_value_email_and_phone():
    email = normalize_findings([raw("email", "Info@Example.COM")])[0]
    assert email.normalized_value == "info@example.com"
    phone = normalize_findings([raw("phone", "+1 (555) 010-4477")])[0]
    assert phone.normalized_value == "+15550104477"


def test_unknown_label_rolls_up_as_unknown():
    (f,) = normalize_findings([raw("mystery blob", "xyz")])
    assert f.canonical_type == "UNKNOWN"
