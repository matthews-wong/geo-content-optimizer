"""Tests for the suggestion layer, including graceful Claude fallback.

No test here touches the network (the autouse ``_no_network`` fixture enforces
that). The Claude path is exercised only for its offline fallback behavior.
"""

from __future__ import annotations

from geooptimizer.score import compute_score
from geooptimizer.suggest import (
    SUGGESTION_THRESHOLD,
    enhance_with_claude,
    generate_suggestions,
    rule_based_suggestions,
)


def test_weak_content_yields_suggestions(weak_text):
    result = compute_score(weak_text)
    suggestions = rule_based_suggestions(result)
    assert suggestions
    assert all(s.source == "rule" for s in suggestions)


def test_suggestions_ordered_by_impact(weak_text):
    result = compute_score(weak_text)
    suggestions = rule_based_suggestions(result)
    impacts = [s.impact for s in suggestions]
    assert impacts == sorted(impacts, reverse=True)


def test_only_under_threshold_signals_suggested(weak_text):
    result = compute_score(weak_text)
    suggested_keys = {s.key for s in rule_based_suggestions(result)}
    for sub in result.sub_scores:
        if sub.score >= SUGGESTION_THRESHOLD:
            assert sub.key not in suggested_keys


def test_enhance_returns_none_without_api_key(monkeypatch, weak_text):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = compute_score(weak_text)
    assert enhance_with_claude(weak_text, result) is None


def test_generate_falls_back_to_rules_without_key(monkeypatch, weak_text):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = compute_score(weak_text)
    suggestions = generate_suggestions(weak_text, result, use_llm=True)
    assert suggestions
    assert all(s.source == "rule" for s in suggestions)


def test_use_llm_false_skips_claude_entirely(weak_text):
    # Even with a key present, use_llm=False must not attempt the network path.
    result = compute_score(weak_text)
    suggestions = generate_suggestions(
        weak_text, result, use_llm=False, api_key="sk-ant-should-not-be-used"
    )
    assert all(s.source == "rule" for s in suggestions)
