"""Tests for the weighted aggregation and the strong-vs-weak contract.

The central promise of the tool is that a GEO-ready article scores materially
higher than a weak one. That contract is asserted here against the real sample
files.
"""

from __future__ import annotations

import pytest

from geooptimizer.score import SIGNALS, GeoResult, compute_score


def test_strong_beats_weak(strong_text, weak_text):
    strong = compute_score(strong_text)
    weak = compute_score(weak_text)
    assert strong.total > weak.total
    # It should be a decisive gap, not a coin-flip.
    assert strong.total - weak.total >= 20.0


def test_strong_is_geo_ready(strong_text):
    assert compute_score(strong_text).total >= 70.0


def test_weak_scores_low(weak_text):
    assert compute_score(weak_text).total < 55.0


def test_total_within_bounds(strong_text, weak_text):
    for text in (strong_text, weak_text):
        assert 0.0 <= compute_score(text).total <= 100.0


def test_total_matches_weighted_sum(strong_text):
    result = compute_score(strong_text)
    expected = round(sum(s.weighted for s in result.sub_scores), 1)
    assert abs(result.total - expected) < 0.2


def test_by_key_and_missing_key(strong_text):
    result = compute_score(strong_text)
    assert result.by_key("statistics").key == "statistics"
    try:
        result.by_key("nonexistent")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for unknown signal key")


def test_weakest_orders_by_impact(strong_text):
    result = compute_score(strong_text)
    weakest = result.weakest()
    impacts = [s.weight * (100.0 - s.score) for s in weakest]
    assert impacts == sorted(impacts, reverse=True)


def test_empty_text_scores_zero_ish():
    result = compute_score("")
    assert isinstance(result, GeoResult)
    assert result.total <= 5.0


@pytest.mark.parametrize(
    "text",
    [
        "   ",            # whitespace only
        "\n\n\t\n",       # blank lines only
        "#",              # bare heading marker, no text
        "# only heading", # heading with no body prose
        "|||",            # malformed table pipes
        "123 456 789",    # digits but no words (word count guard -> no /0)
        "?!.",            # punctuation only
    ],
)
def test_degenerate_input_scores_without_crashing(text):
    """Malformed / near-empty input must score in range, not raise (e.g. div-by-zero)."""
    result = compute_score(text)
    assert isinstance(result, GeoResult)
    assert 0.0 <= result.total <= 100.0
    assert len(result.sub_scores) == len(SIGNALS)
    # Every detector must also stay within its declared [0, 100] contract.
    assert all(0.0 <= s.score <= 100.0 for s in result.sub_scores)


def test_total_equals_weighted_sum_exactly_on_known_input():
    """The aggregate is a pure weighted sum of the sub-scores (no drift)."""
    result = compute_score("# What is X?\n\nX is a tool. It grew 10% in 2023.")
    manual = round(sum(s.score * s.weight for s in result.sub_scores), 1)
    assert result.total == manual
