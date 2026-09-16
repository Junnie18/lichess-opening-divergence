#!/usr/bin/env python3
"""Data collection pipeline for the opening win-rate divergence analysis.

Walks a small opening tree -- four popular first moves, expanded a couple
of plies deep into the most-played replies -- and pulls Lichess win/draw/
loss stats broken out by rating band, plus master-game stats for the same
positions, from the Opening Explorer API. Every response is cached to
data/raw/ by the client, so re-running this script only makes network
calls for positions it hasn't already fetched.

Speed scope: **blitz** is the primary speed (by far the largest sample
sizes across all rating bands on Lichess, so win-rate estimates are least
noisy), with a shallow **rapid** pass over just the first two plies to
sanity-check whether the headline divergence findings are blitz-specific
or hold at a slower time control.

Usage:
    python scripts/collect_data.py [--out data/processed/opening_tree.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.client import ExplorerClient  # noqa: E402
from opening_divergence.notation import uci_list_to_san_line  # noqa: E402
from opening_divergence.tree import candidates_from_response, top_by_popularity  # noqa: E402

ROOT_MOVES_UCI = ["e2e4", "d2d4", "g1f3", "c2c4"]  # 1. e4, 1. d4, 1. Nf3, 1. c4
RATING_BANDS = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]
PRIMARY_SPEED = "blitz"
SECONDARY_SPEED = "rapid"  # only collected for depth <= 1 (see module docstring)
BRANCH_L1 = 3  # top black replies to explore, per first move
BRANCH_L2 = 2  # top white 2nd moves to explore, per level-1 branch
MOVES_PER_QUERY = 12
REFERENCE_BAND_FOR_BRANCHING = 1600  # mid rating; used only to pick *which* replies to expand


def node_record(path_uci: list[str], lichess_by_band: dict, masters: dict | None) -> dict:
    return {
        "path_uci": path_uci,
        "path_san": uci_list_to_san_line(path_uci) if path_uci else "(start)",
        "lichess_by_band": lichess_by_band,
        "masters": masters,
    }


def outcome_dict(outcome) -> dict:
    return {
        "wins": outcome.wins,
        "draws": outcome.draws,
        "losses": outcome.losses,
        "total": outcome.total,
        "win_rate": outcome.win_rate,
        "score": outcome.score,
        "low_confidence": outcome.low_confidence,
    }


def fetch_children_by_band(client: ExplorerClient, path_uci: list[str], speed: str) -> dict:
    """Query one tree position across all rating bands, return
    {band: {uci: outcome_dict}} for its candidate next moves."""
    play = ",".join(path_uci)
    by_band = {}
    for band in RATING_BANDS:
        data = client.lichess(
            play=play,
            speeds=[speed],
            ratings=[band],
            moves=MOVES_PER_QUERY,
        )
        candidates = candidates_from_response(data)
        by_band[str(band)] = {c.uci: {"san": c.san, **outcome_dict(c.outcome)} for c in candidates}
    return by_band


def fetch_children_masters(client: ExplorerClient, path_uci: list[str]) -> dict:
    play = ",".join(path_uci)
    data = client.masters(play=play, moves=MOVES_PER_QUERY)
    candidates = candidates_from_response(data)
    return {c.uci: {"san": c.san, **outcome_dict(c.outcome)} for c in candidates}


def reference_candidates(client: ExplorerClient, path_uci: list[str], speed: str) -> list:
    """Popularity ranking used only to decide which children to expand
    into the next tree level -- fixed to one reference band so the same
    candidate set is compared across all bands (see README)."""
    play = ",".join(path_uci)
    data = client.lichess(
        play=play,
        speeds=[speed],
        ratings=[REFERENCE_BAND_FOR_BRANCHING],
        moves=MOVES_PER_QUERY,
    )
    return candidates_from_response(data)


def build_tree(client: ExplorerClient, speed: str, depth: int) -> list[dict]:
    nodes = []

    # Level 0: root position, before any move. One query per band already
    # covers all candidate first moves; we don't restrict to ROOT_MOVES_UCI
    # here so the raw record shows the full first-move picture.
    root_by_band = fetch_children_by_band(client, [], speed)
    root_masters = fetch_children_masters(client, []) if speed == PRIMARY_SPEED else None
    nodes.append(node_record([], root_by_band, root_masters))

    if depth < 1:
        return nodes

    for first_uci in ROOT_MOVES_UCI:
        path1 = [first_uci]
        by_band_1 = fetch_children_by_band(client, path1, speed)
        masters_1 = fetch_children_masters(client, path1) if speed == PRIMARY_SPEED else None
        nodes.append(node_record(path1, by_band_1, masters_1))

        if depth < 2:
            continue

        ref_children = reference_candidates(client, path1, speed)
        for reply in top_by_popularity(ref_children, BRANCH_L1):
            path2 = path1 + [reply.uci]
            by_band_2 = fetch_children_by_band(client, path2, speed)
            masters_2 = fetch_children_masters(client, path2) if speed == PRIMARY_SPEED else None
            nodes.append(node_record(path2, by_band_2, masters_2))

            if depth < 3:
                continue

            ref_grandchildren = reference_candidates(client, path2, speed)
            for reply2 in top_by_popularity(ref_grandchildren, BRANCH_L2):
                path3 = path2 + [reply2.uci]
                by_band_3 = fetch_children_by_band(client, path3, speed)
                masters_3 = fetch_children_masters(client, path3) if speed == PRIMARY_SPEED else None
                nodes.append(node_record(path3, by_band_3, masters_3))

    return nodes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/processed/opening_tree.json")
    parser.add_argument("--cache-dir", default="data/raw")
    parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Plies past each root move to expand (0-3). Default 3: "
        "first move -> reply -> white's 2nd move, with leaf stats read "
        "off the level-2 response for free.",
    )
    args = parser.parse_args()

    client = ExplorerClient(cache_dir=args.cache_dir)

    print(f"Collecting {PRIMARY_SPEED} data (depth={args.depth})...", file=sys.stderr)
    primary_nodes = build_tree(client, PRIMARY_SPEED, depth=args.depth)

    print(f"Collecting shallow {SECONDARY_SPEED} pass (depth<=1) for cross-check...", file=sys.stderr)
    secondary_nodes = build_tree(client, SECONDARY_SPEED, depth=min(1, args.depth))

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rating_bands": RATING_BANDS,
        "root_moves_uci": ROOT_MOVES_UCI,
        "branching": {"level1": BRANCH_L1, "level2": BRANCH_L2},
        "primary_speed": PRIMARY_SPEED,
        "secondary_speed": SECONDARY_SPEED,
        "nodes": {PRIMARY_SPEED: primary_nodes, SECONDARY_SPEED: secondary_nodes},
        "api_requests_made": client.requests_made,
        "cache_hits": client.cache_hits,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(
        f"Wrote {out_path} ({len(primary_nodes)} {PRIMARY_SPEED} nodes, "
        f"{len(secondary_nodes)} {SECONDARY_SPEED} nodes). "
        f"API requests: {client.requests_made}, cache hits: {client.cache_hits}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
