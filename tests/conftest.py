"""Shared test fixtures. L1 rule: no network, no model, no key."""

from __future__ import annotations

import pytest

from pipeline import compliance, taxonomy


@pytest.fixture(autouse=True)
def _fresh_config_caches():
    """Each test sees config loaded fresh (env overrides work per-test)."""
    taxonomy._reset_cache_for_tests()
    compliance._reset_cache_for_tests()
    yield
    taxonomy._reset_cache_for_tests()
    compliance._reset_cache_for_tests()


class FakeHit:
    """Duck-typed Presidio RecognizerResult."""

    def __init__(self, entity_type: str, start: int, end: int, score: float = 0.85):
        self.entity_type = entity_type
        self.start = start
        self.end = end
        self.score = score


class FakeAnalyzer:
    """Injectable stand-in for presidio_analyzer.AnalyzerEngine."""

    def __init__(self, hits: list[FakeHit]):
        self._hits = hits

    def analyze(self, text: str, language: str):
        return self._hits


@pytest.fixture
def fake_analyzer_factory():
    """Build a FakeAnalyzer from (entity_type, value) pairs found in a text."""

    def build(text: str, wanted: list[tuple[str, str]]) -> FakeAnalyzer:
        hits = []
        for entity_type, value in wanted:
            start = text.index(value)
            hits.append(FakeHit(entity_type, start, start + len(value)))
        return FakeAnalyzer(hits)

    return build
