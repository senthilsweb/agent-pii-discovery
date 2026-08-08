"""L1 corpus-integrity tests for the synthetic PII fixture corpus.

Wraps the assertions in evals/corpus/verify.py so corpus integrity is a
permanent unit-level (L1) gate: every non-null span must slice its document
text exactly, ids must be unique, group counts must match the spec, and all
35 plantable canonical types must be covered across the prose fixtures.

Run:  pytest evals/test_corpus_integrity.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "corpus"))

import verify  # noqa: E402  (evals/corpus/verify.py)


@pytest.fixture(scope="module")
def fixtures() -> list[dict]:
    return verify.load_fixtures()


def test_fixture_ids_unique_and_consistent(fixtures):
    verify.check_ids(fixtures)


def test_group_counts_match_spec(fixtures):
    verify.check_group_counts(fixtures)


def test_every_span_slices_its_document_exactly(fixtures):
    verify.check_spans(fixtures)


def test_expect_and_entity_shape_per_group(fixtures):
    verify.check_expectations(fixtures)


def test_ocr_values_exist_in_source_prose(fixtures):
    verify.check_ocr_sources(fixtures)


def test_all_35_plantable_types_covered_and_tier1_density(fixtures):
    verify.check_coverage(fixtures)


def test_full_verifier_pass():
    verify.run_all()
