"""GEO signal detectors.

Each detector inspects Markdown-flavored content and returns a float sub-score in
``[0, 100]`` measuring how strongly a single GEO signal is present. Detectors are
pure functions of the text — no I/O, no network — so they are fast, deterministic,
and trivially testable.

The signals are the levers that tend to make content quotable by AI answer
engines: a direct up-front answer, question-style headings that match how people
prompt, verifiable statistics, cited sources, clear entities/terms, a concise
summary, scannable list/table structure, and plain-language readability.

``SIGNALS`` is the ordered registry consumed by :mod:`geooptimizer.score`; each
entry carries the detector, its aggregate weight, and a human-readable
description of what it checks.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# --- shared regexes / vocab -------------------------------------------------

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)\S", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)")
_BARE_URL_RE = re.compile(r"(?<!\()\bhttps?://[^\s)]+")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?:\s+|$)")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b")

_QUESTION_STARTERS = (
    "what", "how", "why", "when", "where", "who", "which",
    "can", "does", "do", "is", "are", "should", "will",
)
_DEFINITION_CUES = (
    " is a ", " is an ", " is the ", " are a ", " are the ",
    " refers to ", " is defined as ", " means ", " stands for ",
    " describes ", " is used to ", " is when ",
)
_CITATION_CUES = (
    "according to", "source:", "sources:", "reference", "cited",
    "study", "research", "report", "survey", "et al", "published",
    "data from", "based on",
)
_SUMMARY_CUES = (
    "tl;dr", "tldr", "summary", "in summary", "key takeaway",
    "key takeaways", "key points", "in short", "at a glance",
    "quick answer", "bottom line",
)


def _clamp(value: float) -> float:
    """Clamp a raw score into the ``[0, 100]`` range."""
    return max(0.0, min(100.0, value))


def _word_count(text: str) -> int:
    """Return the number of word tokens in ``text`` (minimum 1 to avoid /0)."""
    return max(1, len(_WORD_RE.findall(text)))


# --- detectors --------------------------------------------------------------


def score_direct_answer(text: str) -> float:
    """Score whether the content opens with a direct answer or definition.

    Answer engines favor content that states the answer up front. This rewards
    definitional phrasing ("X is a...", "X refers to...") appearing early, plus a
    reasonably concise opening paragraph.
    """
    stripped = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ).strip()
    if not stripped:
        return 0.0

    # Look only at the opening ~600 characters — "up front" is the whole point.
    head = stripped[:600].lower()
    cue_hits = sum(1 for cue in _DEFINITION_CUES if cue in head)

    score = min(70.0, cue_hits * 35.0)

    # Reward a crisp opening sentence (answer engines quote short, self-contained
    # statements). First sentence between 5 and 30 words is ideal.
    first_sentence = _SENTENCE_SPLIT_RE.split(stripped, maxsplit=1)[0]
    first_len = len(_WORD_RE.findall(first_sentence))
    if 5 <= first_len <= 30:
        score += 30.0
    elif first_len <= 45:
        score += 15.0

    return _clamp(score)


def score_question_headings(text: str) -> float:
    """Score the presence of question-style headings.

    Question headings mirror how users prompt answer engines, making passages
    easy to match to a query. Scored on how many headings read as questions and
    what fraction of all headings they represent.
    """
    headings = [m.group(2).strip() for m in _HEADING_RE.finditer(text)]
    if not headings:
        return 0.0

    def _is_question(h: str) -> bool:
        lower = h.lower()
        return h.endswith("?") or any(
            lower.startswith(starter + " ") for starter in _QUESTION_STARTERS
        )

    question_headings = [h for h in headings if _is_question(h)]
    count = len(question_headings)
    ratio = count / len(headings)

    # Blend absolute count (caps at 3) and ratio so a doc needs both some
    # question headings and a decent proportion of them.
    count_component = min(1.0, count / 3.0) * 60.0
    ratio_component = ratio * 40.0
    return _clamp(count_component + ratio_component)


def score_statistics(text: str) -> float:
    """Score the density of statistics and concrete numbers.

    Figures, percentages, and dated facts are highly quotable and lend
    authority. Scored on the density of numeric tokens per 100 words, with
    percentages weighted more heavily.
    """
    words = _word_count(text)
    percents = len(_PERCENT_RE.findall(text))
    years = len(_YEAR_RE.findall(text))
    numbers = len(_NUMBER_RE.findall(text))

    # Weight percentages and years above plain numbers; they read as evidence.
    weighted = numbers + percents * 2 + years
    density = weighted / words * 100.0  # weighted numeric tokens per 100 words

    # ~3 weighted numeric tokens per 100 words saturates the signal.
    return _clamp(density / 3.0 * 100.0)


def score_citations(text: str) -> float:
    """Score the presence of citations, sources, and outbound links.

    Content that points to sources is more trustworthy and more citable in turn.
    Scored on links (Markdown or bare URLs) plus explicit sourcing cues
    ("according to", "study", "et al").
    """
    links = len(_MD_LINK_RE.findall(text)) + len(_BARE_URL_RE.findall(text))
    lower = text.lower()
    cue_hits = sum(lower.count(cue) for cue in _CITATION_CUES)

    link_component = min(1.0, links / 3.0) * 60.0
    cue_component = min(1.0, cue_hits / 3.0) * 40.0
    return _clamp(link_component + cue_component)


def score_entities(text: str) -> float:
    """Score entity and key-term clarity.

    Explicitly named entities and emphasized key terms give answer engines clear
    anchors to attach a query to. Scored on the density of proper-noun-like spans
    and bolded terms.
    """
    words = _word_count(text)
    proper_nouns = len(_PROPER_NOUN_RE.findall(text))
    bold_terms = len(_BOLD_RE.findall(text))

    weighted = proper_nouns + bold_terms * 2
    density = weighted / words * 100.0

    # ~5 weighted entity tokens per 100 words saturates the signal.
    return _clamp(density / 5.0 * 100.0)


def score_summary(text: str) -> float:
    """Score the presence of a concise summary / TL;DR.

    A short summary block is prime material for an AI answer. Scored on whether
    summary cues appear, with a bonus when the cue sits near the top of the doc.
    """
    lower = text.lower()
    hits = [cue for cue in _SUMMARY_CUES if cue in lower]
    if not hits:
        return 0.0

    score = min(70.0, len(hits) * 45.0)

    # Bonus if a summary cue appears in the first 20% of the document — a
    # leading TL;DR is worth more than one buried at the end.
    head_cutoff = max(200, len(lower) // 5)
    if any(cue in lower[:head_cutoff] for cue in _SUMMARY_CUES):
        score += 30.0

    return _clamp(score)


def score_structure(text: str) -> float:
    """Score scannable list and table structure.

    Lists and tables chunk information into passage-sized, extractable units.
    Scored on the count of list items and table rows relative to document size.
    """
    list_items = len(_LIST_ITEM_RE.findall(text))
    table_rows = len(_TABLE_ROW_RE.findall(text))

    list_component = min(1.0, list_items / 5.0) * 65.0
    table_component = min(1.0, table_rows / 3.0) * 35.0
    return _clamp(list_component + table_component)


def score_readability(text: str) -> float:
    """Score plain-language readability via a Flesch Reading Ease approximation.

    Concise, plain-language prose is easier for a model to extract cleanly.
    Computes Flesch Reading Ease and maps it to a GEO-friendliness score that
    peaks in the "plain English" band (roughly ease 50-80).
    """
    prose = "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "|"))
    )
    words = _WORD_RE.findall(prose)
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(prose) if s.strip()]
    if len(words) < 5 or not sentences:
        return 0.0

    total_syllables = sum(_count_syllables(w) for w in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = total_syllables / len(words)

    ease = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word

    # Map Flesch ease to a GEO score peaking in the 50-80 "plain English" band.
    if 50.0 <= ease <= 80.0:
        return 100.0
    if ease > 80.0:
        return _clamp(100.0 - (ease - 80.0))  # very simple prose still scores well
    # Below 50: harder text loses points quickly.
    return _clamp(100.0 - (50.0 - ease) * 1.6)


def _count_syllables(word: str) -> int:
    """Estimate the syllable count of an English word (heuristic).

    A vowel-group counter with a silent-``e`` adjustment. Good enough for a
    readability approximation without a pronunciation dictionary.
    """
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


@dataclass(frozen=True)
class SignalSpec:
    """Registry entry describing one GEO signal.

    Attributes:
        key: Machine-readable identifier.
        label: Human-readable name.
        weight: Aggregate weight (all weights sum to 1.0).
        description: What the detector checks, for docs and reports.
        detector: The scoring function, ``str -> float`` in ``[0, 100]``.
    """

    key: str
    label: str
    weight: float
    description: str
    detector: Callable[[str], float]


# Ordered registry. Weights sum to 1.0 (validated in score.py and tests).
SIGNALS: tuple[SignalSpec, ...] = (
    SignalSpec(
        "direct_answer", "Direct answer / definition", 0.18,
        "A clear, self-contained answer or definition stated up front.",
        score_direct_answer,
    ),
    SignalSpec(
        "statistics", "Statistics & numbers", 0.14,
        "Density of concrete figures, percentages, and dated facts.",
        score_statistics,
    ),
    SignalSpec(
        "question_headings", "Question-style headings", 0.12,
        "Headings phrased as the questions users actually ask.",
        score_question_headings,
    ),
    SignalSpec(
        "citations", "Citations & sources", 0.12,
        "Outbound links and explicit sourcing of claims.",
        score_citations,
    ),
    SignalSpec(
        "summary", "Concise summary / TL;DR", 0.12,
        "A short, quotable summary or key-takeaways block.",
        score_summary,
    ),
    SignalSpec(
        "structure", "List & table structure", 0.12,
        "Scannable lists and tables that chunk information.",
        score_structure,
    ),
    SignalSpec(
        "entities", "Entity & term clarity", 0.10,
        "Clearly named entities and emphasized key terms.",
        score_entities,
    ),
    SignalSpec(
        "readability", "Readability", 0.10,
        "Plain-language prose (Flesch Reading Ease approximation).",
        score_readability,
    ),
)
