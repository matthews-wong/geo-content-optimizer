"""Unit tests for the individual GEO signal detectors.

Each detector is a pure function returning a value in [0, 100]. These tests pin
the behavior that matters — presence vs. absence, ordering, and range — without
asserting exact magic numbers that would make the heuristic hard to tune.
"""

from __future__ import annotations

import pytest

from geooptimizer import signals
from geooptimizer.signals import (
    SIGNALS,
    score_citations,
    score_direct_answer,
    score_question_headings,
    score_statistics,
    score_structure,
    score_summary,
)


def test_weights_sum_to_one():
    assert abs(sum(spec.weight for spec in SIGNALS) - 1.0) < 1e-9


def test_signal_keys_are_unique():
    keys = [spec.key for spec in SIGNALS]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("spec", SIGNALS, ids=[s.key for s in SIGNALS])
def test_detector_output_in_range(spec):
    sample = "# What is a widget?\n\nA widget is a small tool. It costs 42%."
    value = spec.detector(sample)
    assert 0.0 <= value <= 100.0


def test_direct_answer_rewards_up_front_definition():
    with_def = "A widget is a small measuring tool used in labs."
    without_def = (
        "Well, there are many things one could possibly say about the general "
        "topic at hand before getting anywhere near an actual point worth making."
    )
    assert score_direct_answer(with_def) > score_direct_answer(without_def)


def test_question_headings_detects_questions():
    questions = "## How does it work?\n\n## Why does it matter?\n"
    statements = "## Overview\n\n## Background\n"
    assert score_question_headings(questions) > score_question_headings(statements)


def test_question_headings_zero_without_headings():
    assert score_question_headings("Just a paragraph with no headings at all.") == 0.0


def test_statistics_rewards_numbers_and_percentages():
    with_stats = "Revenue grew 42% in 2023, reaching 1,200 units across 3 regions."
    without_stats = "Revenue grew a lot this year across many different regions."
    assert score_statistics(with_stats) > score_statistics(without_stats)


def test_citations_rewards_links_and_cues():
    cited = (
        "According to a 2023 study, adoption rose. See "
        "[the report](https://example.com/report) and https://example.org/data."
    )
    uncited = "Adoption rose a lot, or so people generally seem to believe."
    assert score_citations(cited) > score_citations(uncited)


def test_summary_detects_tldr():
    with_tldr = "# Title\n\n## TL;DR\n\n- Key point one.\n- Key point two."
    without_tldr = "# Title\n\nA long meandering introduction that never gets to the point."
    assert score_summary(with_tldr) > score_summary(without_tldr)
    assert score_summary(without_tldr) == 0.0


def test_structure_rewards_lists_and_tables():
    structured = (
        "- item one\n- item two\n- item three\n- item four\n- item five\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    )
    prose = "This is a single block of prose with no list items or tables anywhere."
    assert score_structure(structured) > score_structure(prose)


def test_readability_penalizes_long_dense_sentences():
    plain = "Widgets are small. They help you work. Most people like them a lot."
    dense = (
        "Notwithstanding the aforementioned considerations, the multifarious "
        "ramifications of the phenomenon necessitate a comprehensive "
        "reevaluation of our epistemological presuppositions regarding "
        "instrumentation and its concomitant methodological implications."
    )
    assert signals.score_readability(plain) > signals.score_readability(dense)


def test_syllable_counter_handles_silent_e():
    assert signals._count_syllables("make") == 1
    assert signals._count_syllables("banana") == 3
    assert signals._count_syllables("the") == 1
