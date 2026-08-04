"""Weighted aggregation of GEO signals into a single 0-100 score.

Runs every detector in :data:`geooptimizer.signals.SIGNALS`, then combines the
sub-scores using each signal's weight. The result is a transparent linear model:
``total = sum(sub_score_i * weight_i)``. No detector or the aggregate ever
touches the network, so scoring is fully offline and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from geooptimizer.signals import SIGNALS

# Guard against the registry weights drifting away from a proper distribution.
_WEIGHT_SUM = sum(spec.weight for spec in SIGNALS)
if abs(_WEIGHT_SUM - 1.0) > 1e-9:  # pragma: no cover - configuration invariant
    raise ValueError(f"Signal weights must sum to 1.0, got {_WEIGHT_SUM:.6f}")


@dataclass(frozen=True)
class SubScore:
    """One signal's contribution to the overall GEO score.

    Attributes:
        key: Signal identifier.
        label: Human-readable signal name.
        weight: Aggregate weight applied to ``score``.
        score: Detector output in ``[0, 100]``.
        description: What the signal checks.
    """

    key: str
    label: str
    weight: float
    score: float
    description: str

    @property
    def weighted(self) -> float:
        """This signal's points contributed to the 0-100 total."""
        return self.score * self.weight


@dataclass(frozen=True)
class GeoResult:
    """The full result of scoring one piece of content.

    Attributes:
        total: Overall GEO score in ``[0, 100]``.
        sub_scores: Per-signal breakdown, in registry order.
    """

    total: float
    sub_scores: list[SubScore] = field(default_factory=list)

    def by_key(self, key: str) -> SubScore:
        """Return the sub-score for ``key``.

        Raises:
            KeyError: If no signal with that key was scored.
        """
        for sub in self.sub_scores:
            if sub.key == key:
                return sub
        raise KeyError(key)

    def weakest(self) -> list[SubScore]:
        """Sub-scores ordered by improvement impact (weight * gap), worst first.

        The gap is ``100 - score``; multiplying by weight ranks signals by how
        many points fixing them could add to the total — the natural priority
        order for suggestions.
        """
        return sorted(
            self.sub_scores,
            key=lambda s: s.weight * (100.0 - s.score),
            reverse=True,
        )


def compute_score(text: str) -> GeoResult:
    """Score ``text`` against every GEO signal and aggregate the result.

    Args:
        text: Markdown-flavored content (see :func:`geooptimizer.io_utils.load_content`).

    Returns:
        A :class:`GeoResult` with the weighted total and per-signal breakdown.
    """
    sub_scores: list[SubScore] = []
    total = 0.0

    for spec in SIGNALS:
        raw = float(spec.detector(text))
        score = max(0.0, min(100.0, raw))
        sub = SubScore(
            key=spec.key,
            label=spec.label,
            weight=spec.weight,
            score=score,
            description=spec.description,
        )
        sub_scores.append(sub)
        total += sub.weighted

    return GeoResult(total=round(total, 1), sub_scores=sub_scores)
