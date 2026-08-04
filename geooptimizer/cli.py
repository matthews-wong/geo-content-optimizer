"""Command-line interface for geo-content-optimizer.

Wires the offline scoring pipeline (:func:`geooptimizer.io_utils.load_content`
-> :func:`geooptimizer.score.compute_score`) and the suggestion layer
(:func:`geooptimizer.suggest.generate_suggestions`) into a single Click command.

Accepts Markdown (``.md``), HTML (``.html``/``.htm``), and plain-text (``.txt``)
inputs. All scoring is offline; the optional Claude enhancement is opt-out via
``--no-llm`` and degrades gracefully to the rule-based path when no API key is
set.
"""

from __future__ import annotations

import json
import sys

import click

from geooptimizer import __version__
from geooptimizer.io_utils import load_content
from geooptimizer.score import GeoResult, compute_score
from geooptimizer.suggest import Suggestion, generate_suggestions


def _grade(total: float) -> str:
    """Map a 0-100 GEO score to a coarse letter-style band for quick reading."""
    if total >= 85:
        return "A - highly GEO-ready"
    if total >= 70:
        return "B - GEO-ready"
    if total >= 55:
        return "C - needs work"
    if total >= 40:
        return "D - weak"
    return "F - poor"


def _bar(score: float, width: int = 20) -> str:
    """Render a fixed-width text meter for a 0-100 sub-score."""
    filled = int(round(score / 100.0 * width))
    return "#" * filled + "-" * (width - filled)


def _result_to_dict(
    result: GeoResult, suggestions: list[Suggestion]
) -> dict:
    """Serialize a scored result and its suggestions to a JSON-ready dict."""
    return {
        "total": result.total,
        "grade": _grade(result.total),
        "sub_scores": [
            {
                "key": s.key,
                "label": s.label,
                "weight": s.weight,
                "score": round(s.score, 1),
                "weighted": round(s.weighted, 1),
                "description": s.description,
            }
            for s in result.sub_scores
        ],
        "suggestions": [
            {
                "key": s.key,
                "label": s.label,
                "message": s.message,
                "impact": s.impact,
                "source": s.source,
            }
            for s in suggestions
        ],
    }


def _render_text(result: GeoResult, suggestions: list[Suggestion]) -> str:
    """Render a human-readable report for the terminal."""
    lines: list[str] = []
    lines.append(f"GEO score: {result.total:.1f}/100  [{_grade(result.total)}]")
    lines.append("")
    lines.append("Signal breakdown:")
    for sub in result.sub_scores:
        lines.append(
            f"  {sub.label:<28} {sub.score:5.1f}  {_bar(sub.score)}  "
            f"(w={sub.weight:.2f})"
        )

    lines.append("")
    if suggestions:
        source = suggestions[0].source
        origin = "Claude" if source == "claude" else "rule-based"
        lines.append(f"Top suggestions ({origin}):")
        for i, sug in enumerate(suggestions, start=1):
            lines.append(f"  {i}. [{sug.label}] (+{sug.impact:.1f} pts)")
            lines.append(f"     {sug.message}")
    else:
        lines.append("No suggestions - every signal is above threshold. Nice.")

    return "\n".join(lines)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the full result as JSON instead of a text report.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Disable the optional Claude enhancement (rule-based suggestions only).",
)
@click.version_option(version=__version__, prog_name="geo-content-optimizer")
def main(path: str, as_json: bool, no_llm: bool) -> None:
    """Score a content file for Generative Engine Optimization (GEO).

    PATH is a .md, .html, or .txt file. Prints a 0-100 GEO score, a weighted
    per-signal breakdown, and prioritized improvement suggestions.
    """
    try:
        text = load_content(path)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    result = compute_score(text)
    suggestions = generate_suggestions(text, result, use_llm=not no_llm)

    if as_json:
        click.echo(json.dumps(_result_to_dict(result, suggestions), indent=2))
    else:
        click.echo(_render_text(result, suggestions))


if __name__ == "__main__":  # pragma: no cover
    main.main(sys.argv[1:])
