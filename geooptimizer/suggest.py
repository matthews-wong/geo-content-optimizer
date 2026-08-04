"""Improvement suggestions for a scored piece of content.

Two layers:

1. **Rule-based** (default, fully offline): for every signal scoring below a
   threshold, emit a concrete, templated suggestion, prioritized by how many
   points fixing it could add to the total.
2. **Claude-enhanced** (optional): when ``ANTHROPIC_API_KEY`` is set and the
   ``anthropic`` SDK is installed, ask Claude (model ``claude-sonnet-5``) for
   targeted rewrite ideas. Any failure — missing key, missing package, network
   or API error — falls back silently to the rule-based suggestions. The API is
   never touched at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from geooptimizer.score import GeoResult

# A signal at or above this sub-score is considered "good enough" to skip.
SUGGESTION_THRESHOLD = 65.0

# The model used for the optional rewrite-suggestion path. Sonnet is a good fit
# for high-volume, low-stakes rewriting; the tool works fully without it.
CLAUDE_MODEL = "claude-sonnet-5"

# Rule-based advice keyed by signal. Kept deliberately concrete and actionable.
_ADVICE: dict[str, str] = {
    "direct_answer": (
        "Lead with a one- to two-sentence direct answer or definition before any "
        "preamble. Answer engines quote the first self-contained statement they find."
    ),
    "statistics": (
        "Add concrete figures, percentages, and dated facts. Specific numbers are "
        "far more quotable than vague qualifiers like 'many' or 'often'."
    ),
    "question_headings": (
        "Rewrite section headings as the questions users actually ask "
        "(e.g. 'How does X work?'). This matches passages to real prompts."
    ),
    "citations": (
        "Cite your sources with outbound links and attributions ('according to', "
        "study/report references). Sourced claims are more trustworthy and citable."
    ),
    "summary": (
        "Add a short TL;DR or key-takeaways block near the top. A concise summary "
        "is prime material for an AI-generated answer."
    ),
    "structure": (
        "Break dense prose into bulleted lists and comparison tables. Chunked "
        "content is easier to extract as a passage."
    ),
    "entities": (
        "Name key entities explicitly and bold important terms rather than relying "
        "on pronouns. Clear anchors help engines match a query to your content."
    ),
    "readability": (
        "Shorten sentences and prefer plain words. Aim for clear, plain-English "
        "prose that a model can extract cleanly."
    ),
}


@dataclass(frozen=True)
class Suggestion:
    """A single prioritized improvement suggestion.

    Attributes:
        key: The signal this suggestion targets.
        label: Human-readable signal name.
        message: The actionable advice.
        impact: Estimated points recoverable (``weight * (100 - score)``).
        source: ``"rule"`` or ``"claude"``.
    """

    key: str
    label: str
    message: str
    impact: float
    source: str = "rule"


def rule_based_suggestions(result: GeoResult) -> list[Suggestion]:
    """Build offline suggestions for every under-threshold signal.

    Args:
        result: A scored :class:`GeoResult`.

    Returns:
        Suggestions ordered by descending improvement impact.
    """
    suggestions: list[Suggestion] = []
    for sub in result.weakest():
        if sub.score >= SUGGESTION_THRESHOLD:
            continue
        suggestions.append(
            Suggestion(
                key=sub.key,
                label=sub.label,
                message=_ADVICE.get(sub.key, "Improve this signal."),
                impact=round(sub.weight * (100.0 - sub.score), 1),
                source="rule",
            )
        )
    return suggestions


def enhance_with_claude(
    text: str,
    result: GeoResult,
    *,
    api_key: str | None = None,
) -> list[Suggestion] | None:
    """Ask Claude for targeted rewrite suggestions, or return ``None`` on any failure.

    This is the optional enhancement path. It returns ``None`` — signalling the
    caller to fall back to the rule-based suggestions — whenever the API key is
    absent, the SDK is not installed, or the request fails for any reason.

    Args:
        text: The content being analyzed.
        result: The scored :class:`GeoResult`.
        api_key: Explicit key; defaults to the ``ANTHROPIC_API_KEY`` env var.

    Returns:
        A list of Claude-sourced suggestions, or ``None`` to trigger fallback.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None

    try:
        import anthropic  # imported lazily so the offline path never needs it
    except ImportError:
        return None

    # Focus the model on the signals that actually need work.
    weak = [s for s in result.weakest() if s.score < SUGGESTION_THRESHOLD]
    if not weak:
        return []

    weak_summary = "\n".join(f"- {s.label}: {s.score:.0f}/100" for s in weak)
    prompt = (
        "You are a Generative Engine Optimization (GEO) editor. Given the "
        "content below and its weakest GEO signals, propose one concrete, "
        "specific rewrite suggestion per weak signal. Return each suggestion on "
        "its own line, prefixed with the signal name in square brackets, e.g. "
        "'[Statistics & numbers] ...'. Be concrete and reference the content.\n\n"
        f"Weakest signals:\n{weak_summary}\n\n"
        f"Content:\n{text[:6000]}"
    )

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        # Network errors, auth errors, rate limits — degrade gracefully.
        return None

    lines = [
        block.text for block in response.content if getattr(block, "type", "") == "text"
    ]
    body = "\n".join(lines).strip()
    if not body:
        return None

    # Map returned lines back onto weak signals by label prefix; fall back to
    # attaching leftovers to the highest-impact weak signal.
    label_to_sub = {s.label: s for s in weak}
    suggestions: list[Suggestion] = []
    for line in (ln.strip() for ln in body.splitlines() if ln.strip()):
        matched = next((s for lbl, s in label_to_sub.items() if lbl in line), weak[0])
        message = line.split("]", 1)[-1].strip() if line.startswith("[") else line
        suggestions.append(
            Suggestion(
                key=matched.key,
                label=matched.label,
                message=message,
                impact=round(matched.weight * (100.0 - matched.score), 1),
                source="claude",
            )
        )
    return suggestions or None


def generate_suggestions(
    text: str,
    result: GeoResult,
    *,
    use_llm: bool = True,
    api_key: str | None = None,
) -> list[Suggestion]:
    """Return improvement suggestions, using Claude when available.

    Args:
        text: The content being analyzed.
        result: The scored :class:`GeoResult`.
        use_llm: If ``True``, attempt the Claude path before falling back.
        api_key: Explicit key; defaults to the ``ANTHROPIC_API_KEY`` env var.

    Returns:
        Suggestions ordered by descending improvement impact. Always non-empty
        when at least one signal is under threshold.
    """
    if use_llm:
        enhanced = enhance_with_claude(text, result, api_key=api_key)
        if enhanced is not None:
            return enhanced
    return rule_based_suggestions(result)
