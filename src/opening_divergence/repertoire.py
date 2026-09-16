"""Pure logic behind scripts/counter_repertoire.py, split out so it can be
unit-tested without a network call or a CLI invocation.
"""

from __future__ import annotations

from .tree import CandidateMove

RATING_BAND_BOUNDARIES = [0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]


def nearest_band(rating: int) -> int:
    """Map an arbitrary rating to the explorer's rating-band boundaries
    (each band covers [boundary, next boundary))."""
    below_or_equal = [b for b in RATING_BAND_BOUNDARIES if b <= rating]
    return max(below_or_equal) if below_or_equal else RATING_BAND_BOUNDARIES[0]


def own_score(candidate: CandidateMove, mover_is_white: bool) -> float:
    """Expected score for whoever is about to move, converting from the
    API's always-White-perspective score."""
    return candidate.outcome.score if mover_is_white else (1 - candidate.outcome.score)


def rank_candidates(candidates: list[CandidateMove], mover_is_white: bool) -> list[CandidateMove]:
    playable = [c for c in candidates if c.outcome.total > 0]
    return sorted(playable, key=lambda c: own_score(c, mover_is_white), reverse=True)
