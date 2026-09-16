"""Helpers for turning an Opening Explorer JSON response into candidate
moves with their MoveOutcome stats, used by both the data collection
pipeline and the counter-repertoire CLI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .stats import MoveOutcome


@dataclass(frozen=True)
class CandidateMove:
    uci: str
    san: str
    outcome: MoveOutcome
    average_rating: int | None = None


def candidates_from_response(data: dict) -> list[CandidateMove]:
    """Extract the candidate next moves (and their outcomes) from a raw
    /lichess or /masters explorer response."""
    candidates = []
    for m in data.get("moves", []):
        outcome = MoveOutcome(
            label=m["san"],
            wins=m["white"],
            draws=m["draws"],
            losses=m["black"],
        )
        candidates.append(
            CandidateMove(
                uci=m["uci"],
                san=m["san"],
                outcome=outcome,
                average_rating=m.get("averageRating"),
            )
        )
    return candidates


def top_by_popularity(candidates: list[CandidateMove], n: int) -> list[CandidateMove]:
    return sorted(candidates, key=lambda c: c.outcome.total, reverse=True)[:n]


def find_by_uci(candidates: list[CandidateMove], uci: str) -> CandidateMove | None:
    for c in candidates:
        if c.uci == uci:
            return c
    return None
