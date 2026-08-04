"""geo-content-optimizer: a heuristic scorer for Generative Engine Optimization (GEO).

This package analyzes a piece of content and estimates how likely it is to be
surfaced or cited by AI answer engines. It inspects concrete, content-level GEO
signals (direct answers, question headings, statistics, citations, entity
clarity, a concise summary, list/table structure, readability), combines them
into a weighted 0-100 GEO score, and emits prioritized, actionable suggestions.

The scoring model is a transparent heuristic, not a learned model or a live
answer-engine feedback loop. See the README for an honest description of its
limits. All analysis runs fully offline; the optional Claude-powered rewrite
suggestions degrade gracefully to the rule-based path when no API key is set.
"""

from geooptimizer.score import GeoResult, SubScore, compute_score
from geooptimizer.signals import SIGNALS
from geooptimizer.suggest import Suggestion, generate_suggestions

__version__ = "0.1.0"

__all__ = [
    "GeoResult",
    "SubScore",
    "Suggestion",
    "SIGNALS",
    "compute_score",
    "generate_suggestions",
    "__version__",
]
