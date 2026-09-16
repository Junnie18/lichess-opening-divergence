"""Win-rate / confidence math shared by the analysis scripts and the CLI.

Terminology: "score" means expected score from White's point of view --
``(wins + 0.5 * draws) / total`` -- the standard chess convention for
evaluating a move, since it correctly treats a draw as half a point rather
than discarding it (raw win-rate alone hides moves that draw heavily but
rarely lose). "win rate" (``wins / total``) is also exposed since the task
and most players talk in those terms, but ranking uses ``score`` unless
noted otherwise -- this is a documented assumption, not a hidden default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SAMPLE_SIZE = 30
Z_95 = 1.959963985


@dataclass(frozen=True)
class MoveOutcome:
    label: str
    wins: int
    draws: int
    losses: int

    @property
    def total(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def win_rate(self) -> float | None:
        if self.total == 0:
            return None
        return self.wins / self.total

    @property
    def score(self) -> float | None:
        if self.total == 0:
            return None
        return (self.wins + 0.5 * self.draws) / self.total

    @property
    def low_confidence(self) -> bool:
        return self.total < MIN_SAMPLE_SIZE


def wilson_interval(p: float, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion ``p`` estimated from ``n`` trials."""
    if n == 0:
        return (0.0, 1.0)
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return max(0.0, lo), min(1.0, hi)


def score_confidence_interval(outcome: MoveOutcome, z: float = Z_95) -> tuple[float, float] | None:
    if outcome.total == 0:
        return None
    return wilson_interval(outcome.score, outcome.total, z=z)


def _standard_error(p: float, n: int) -> float:
    if n == 0:
        return float("inf")
    return math.sqrt(max(p * (1 - p), 1e-9) / n)


def is_significantly_different(a: MoveOutcome, b: MoveOutcome, z: float = Z_95) -> bool:
    """Two-proportion z-test comparing expected scores.

    Treats each move's score as an approximately-normal sample proportion in
    [0, 1] (valid via the CLT for reasonably large ``n``, even though draws
    contribute 0.5 rather than a hard 0/1 outcome). Returns False (not
    significant) whenever either side has zero games.
    """
    if a.total == 0 or b.total == 0:
        return False
    se = math.sqrt(_standard_error(a.score, a.total) ** 2 + _standard_error(b.score, b.total) ** 2)
    if se == 0:
        return a.score != b.score
    return abs(a.score - b.score) > z * se


def confident_ranking(
    outcomes: list[MoveOutcome], min_sample_size: int = MIN_SAMPLE_SIZE
) -> list[MoveOutcome]:
    """Sort outcomes by score, descending, but only among those meeting the
    minimum sample size. Outcomes below the threshold are dropped -- callers
    that want to display them anyway should say so explicitly, flagged as
    low-confidence.
    """
    eligible = [o for o in outcomes if o.total >= min_sample_size]
    return sorted(eligible, key=lambda o: o.score, reverse=True)
