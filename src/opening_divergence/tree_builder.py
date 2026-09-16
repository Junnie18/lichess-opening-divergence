"""Popularity-pruned BFS opening-tree construction.

Builds the list of positions (move sequences) the pipeline collects stats
for. Kept decoupled from the network client: callers pass a
``get_candidates`` function (``path_uci -> list[CandidateMove]``), so this
module is fully unit-testable against a synthetic in-memory "opening book"
fixture with no HTTP calls.

Design (see README / docs/findings.md for the full rationale):

- Start from a set of *seeds* -- named systems anchored a few plies in
  (Sicilian, French, Ruy Lopez, ...) plus the four bare first moves.
- From each seed, expand forward via BFS, at each ply keeping only the
  most popular candidate replies (bounded by ``branch_factor``) that also
  clear ``min_popularity_share`` of the games at that position -- this is
  the "popularity threshold" pruning the project brief asks for, so a
  single 0.1%-of-games sideline can't blow up the tree.
- Popularity to decide branching is read from ONE reference query per
  position (a fixed reference band/speed/window), never from the
  validation window -- picking *which positions to test* using
  validation-window data would leak information into the supposedly
  held-out replication check. All windows/bands/speeds are then queried
  for stats at this same fixed set of positions.
- The same position can be reachable from more than one seed (e.g. a
  generic 1.e4 expansion can rediscover 1.e4 c5, the Sicilian seed); such
  positions are de-duplicated by path, keeping every seed system that
  reached them (used later for the outlier/concentration check: a
  recommendation resting on positions from only one system is more
  fragile than one corroborated across several).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .notation import uci_list_to_san_line
from .tree import CandidateMove

GetCandidates = Callable[[list[str]], list[CandidateMove]]


@dataclass(frozen=True)
class Seed:
    system: str
    path_uci: list[str]
    extra_depth: int  # plies to expand *beyond* this seed's own position


@dataclass
class TreeNode:
    path_uci: list[str]
    path_san: str
    systems: list[str] = field(default_factory=list)  # every seed system that reached this position

    @property
    def path_key(self) -> tuple[str, ...]:
        return tuple(self.path_uci)


def _prune(candidates: list[CandidateMove], branch_factor: int, min_share: float) -> list[CandidateMove]:
    total = sum(c.outcome.total for c in candidates)
    if total == 0:
        return []
    ranked = sorted(candidates, key=lambda c: c.outcome.total, reverse=True)
    qualified = [c for c in ranked if c.outcome.total / total >= min_share]
    return qualified[:branch_factor]


def build_positions(
    seeds: list[Seed],
    get_candidates: GetCandidates,
    branch_factor: int = 2,
    min_popularity_share: float = 0.02,
) -> list[TreeNode]:
    """BFS-expand every seed; return de-duplicated positions in discovery
    order (seed order, then breadth-first within each seed)."""
    nodes_by_path: dict[tuple[str, ...], TreeNode] = {}

    for seed in seeds:
        # BFS queue holds (path_uci, plies_remaining_for_this_seed).
        queue: deque[tuple[list[str], int]] = deque([(list(seed.path_uci), seed.extra_depth)])
        seen_this_seed: set[tuple[str, ...]] = set()

        while queue:
            path, remaining = queue.popleft()
            key = tuple(path)
            if key in seen_this_seed:
                continue
            seen_this_seed.add(key)

            existing = nodes_by_path.get(key)
            if existing is None:
                existing = TreeNode(
                    path_uci=path,
                    path_san=uci_list_to_san_line(path) if path else "(start)",
                )
                nodes_by_path[key] = existing
            if seed.system not in existing.systems:
                existing.systems.append(seed.system)

            if remaining <= 0:
                continue

            candidates = get_candidates(path)
            children = _prune(candidates, branch_factor, min_popularity_share)
            for child in children:
                queue.append((path + [child.uci], remaining - 1))

    # Stable order: sort by (depth, path) so output is deterministic given
    # deterministic candidate ordering from get_candidates.
    return sorted(nodes_by_path.values(), key=lambda n: (len(n.path_uci), n.path_uci))
