#!/usr/bin/env python3
"""Data collection pipeline for the opening win-rate divergence analysis.

Rewritten for out-of-sample validation and cross-speed / cross-band rigor
(see docs/findings.md for the full methodology write-up). Key design:

- **Tree**: BFS-expanded from 12 named seeds (the 4 bare first moves --
  e4/d4/Nf3/c4 -- plus 8 systems anchored a few plies in: Sicilian,
  French, Caro-Kann, Ruy Lopez, Italian, Queen's Gambit, King's
  Indian/Grunfeld, English), popularity-pruned (see tree_builder.py).
  Which positions to test is decided ONCE from discovery-window reference
  data; the exact same position set is then queried across every band,
  speed, and window below -- no window/band/speed sees a different
  candidate set than any other for the same position.
- **Time windows**: DISCOVERY_SINCE..DISCOVERY_UNTIL is mined for
  everything (tree structure + all headline candidate findings);
  VALIDATION_SINCE..VALIDATION_UNTIL is queried ONLY to re-test findings
  already made in discovery -- see scripts/validate_findings.py. The two
  windows are strictly non-overlapping by construction.
- **Placebo windows**: PLACEBO_MONTH_A/B are two adjacent months squarely
  inside the discovery period (minimal chess-meta drift between them, vs.
  comparing early-discovery to late-discovery which would confound "the
  pipeline is miscalibrated" with "the actual meta shifted over years").
  Used by scripts/placebo_check.py to calibrate the false-positive rate.
- **Speeds**: blitz is primary (largest samples; gets the full
  band x window matrix). rapid and classical are collected discovery-only,
  across the same band set, as a same-window cross-speed check -- see
  docs/findings.md for whether headline findings replicate across speeds.
- **Masters**: unwindowed by band/speed (doesn't have those axes) but
  restricted to since=DISCOVERY_SINCE/until=VALIDATION_UNTIL so it's
  scoped to the same modern era as the rest of the study rather than all
  of recorded chess history.

Every response is cached to data/raw/ by the client, so re-running this
script (or resuming after an interruption) only makes network calls for
requests it hasn't already made.

Usage:
    python scripts/collect_data.py --dry-run          # tree size + request budget estimate, no fetching
    python scripts/collect_data.py                    # full collection
    python scripts/collect_data.py --skip-secondary-speeds --skip-placebo   # blitz D+V only
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.client import ExplorerAuthError, ExplorerClient  # noqa: E402
from opening_divergence.notation import parse_move_text  # noqa: E402
from opening_divergence.tree import candidates_from_response  # noqa: E402
from opening_divergence.tree_builder import Seed, build_positions  # noqa: E402

RATING_BANDS = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]
PRIMARY_SPEED = "blitz"
SECONDARY_SPEEDS = ["rapid", "classical"]
MOVES_PER_QUERY = 12

REFERENCE_BAND_FOR_BRANCHING = 1600
BRANCH_FACTOR = 2
MIN_POPULARITY_SHARE = 0.02

DISCOVERY_SINCE, DISCOVERY_UNTIL = "2016-01", "2022-12"
VALIDATION_SINCE, VALIDATION_UNTIL = "2023-01", "2026-08"
PLACEBO_MONTH_A, PLACEBO_MONTH_B = "2021-06", "2021-07"  # adjacent months inside discovery

SEEDS_SAN: list[tuple[str, str, int]] = [
    # (system label, SAN move sequence, extra plies to BFS-expand beyond it)
    ("e4", "e4", 5),
    ("d4", "d4", 5),
    ("Nf3", "Nf3", 5),
    ("c4", "c4", 5),
    ("Sicilian", "e4 c5", 4),
    ("French", "e4 e6", 4),
    ("Caro-Kann", "e4 c6", 4),
    ("Ruy Lopez", "e4 e5 Nf3 Nc6 Bb5", 4),
    ("Italian", "e4 e5 Nf3 Nc6 Bc4", 4),
    ("Queen's Gambit", "d4 d5 c4 e6", 4),
    ("King's Indian / Grunfeld", "d4 Nf6 c4 g6", 4),
    ("English (reversed Sicilian)", "c4 e5", 4),
]


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


def moves_dict(data: dict) -> dict:
    return {c.uci: {"san": c.san, **outcome_dict(c.outcome)} for c in candidates_from_response(data)}


def build_seeds() -> list[Seed]:
    return [
        Seed(system=label, path_uci=parse_move_text(san), extra_depth=depth)
        for label, san, depth in SEEDS_SAN
    ]


def make_reference_get_candidates(client: ExplorerClient):
    def get_candidates(path_uci: list[str]):
        data = client.lichess(
            play=",".join(path_uci),
            speeds=[PRIMARY_SPEED],
            ratings=[REFERENCE_BAND_FOR_BRANCHING],
            since=DISCOVERY_SINCE,
            until=DISCOVERY_UNTIL,
            moves=MOVES_PER_QUERY,
        )
        return candidates_from_response(data)

    return get_candidates


def estimate_request_budget(n_nodes: int, args) -> dict:
    blitz_dv = n_nodes * len(RATING_BANDS) * 2  # discovery + validation
    secondary = 0 if args.skip_secondary_speeds else n_nodes * len(RATING_BANDS) * len(SECONDARY_SPEEDS)
    masters = 0 if args.skip_masters else n_nodes
    placebo = 0 if args.skip_placebo else n_nodes * 2  # month A + month B, at reference band only
    total = blitz_dv + secondary + masters + placebo
    return {
        "blitz_discovery_and_validation": blitz_dv,
        "secondary_speeds_discovery_only": secondary,
        "masters": masters,
        "placebo": placebo,
        "total_requests": total,
        "estimated_minutes_at_1rps": round(total / 60, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default="data/processed/opening_tree.json")
    parser.add_argument("--cache-dir", default="data/raw")
    parser.add_argument("--branch-factor", type=int, default=BRANCH_FACTOR)
    parser.add_argument("--min-share", type=float, default=MIN_POPULARITY_SHARE)
    parser.add_argument(
        "--dry-run", action="store_true", help="Build the tree and print size/budget, fetch nothing else."
    )
    parser.add_argument("--skip-secondary-speeds", action="store_true")
    parser.add_argument("--skip-masters", action="store_true")
    parser.add_argument("--skip-placebo", action="store_true")
    args = parser.parse_args()

    client = ExplorerClient(cache_dir=args.cache_dir)

    print("Building opening tree from discovery-window reference popularity...", file=sys.stderr)
    seeds = build_seeds()
    try:
        positions = build_positions(
            seeds,
            make_reference_get_candidates(client),
            branch_factor=args.branch_factor,
            min_popularity_share=args.min_share,
        )
    except ExplorerAuthError as e:
        print(str(e), file=sys.stderr)
        return 1

    depth_hist = Counter(len(n.path_uci) for n in positions)
    system_hist = Counter(sys_name for n in positions for sys_name in n.systems)
    budget = estimate_request_budget(len(positions), args)

    print(f"Tree: {len(positions)} distinct positions.", file=sys.stderr)
    print(f"  by depth (plies): {dict(sorted(depth_hist.items()))}", file=sys.stderr)
    print(f"  by system: {dict(sorted(system_hist.items(), key=lambda kv: -kv[1]))}", file=sys.stderr)
    print(f"  request budget estimate: {json.dumps(budget)}", file=sys.stderr)
    print(
        f"  reference-query requests so far: {client.requests_made} ({client.cache_hits} cache hits)",
        file=sys.stderr,
    )

    if args.dry_run:
        return 0

    nodes_out = []
    total_positions = len(positions)
    for i, node in enumerate(positions, start=1):
        play = ",".join(node.path_uci)
        print(f"[{i}/{total_positions}] {node.path_san or '(start)'}", file=sys.stderr)

        lichess_blitz = {"discovery": {}, "validation": {}}
        for band in RATING_BANDS:
            for window_name, since, until in [
                ("discovery", DISCOVERY_SINCE, DISCOVERY_UNTIL),
                ("validation", VALIDATION_SINCE, VALIDATION_UNTIL),
            ]:
                data = client.lichess(
                    play=play,
                    speeds=[PRIMARY_SPEED],
                    ratings=[band],
                    since=since,
                    until=until,
                    moves=MOVES_PER_QUERY,
                )
                lichess_blitz[window_name][str(band)] = moves_dict(data)

        lichess_secondary = {}
        if not args.skip_secondary_speeds:
            for speed in SECONDARY_SPEEDS:
                lichess_secondary[speed] = {}
                for band in RATING_BANDS:
                    data = client.lichess(
                        play=play,
                        speeds=[speed],
                        ratings=[band],
                        since=DISCOVERY_SINCE,
                        until=DISCOVERY_UNTIL,
                        moves=MOVES_PER_QUERY,
                    )
                    lichess_secondary[speed][str(band)] = moves_dict(data)

        masters = None
        if not args.skip_masters:
            data = client.masters(
                play=play, moves=MOVES_PER_QUERY, since=DISCOVERY_SINCE, until=VALIDATION_UNTIL
            )
            masters = moves_dict(data)

        placebo = None
        if not args.skip_placebo:
            data_a = client.lichess(
                play=play,
                speeds=[PRIMARY_SPEED],
                ratings=[REFERENCE_BAND_FOR_BRANCHING],
                since=PLACEBO_MONTH_A,
                until=PLACEBO_MONTH_A,
                moves=MOVES_PER_QUERY,
            )
            data_b = client.lichess(
                play=play,
                speeds=[PRIMARY_SPEED],
                ratings=[REFERENCE_BAND_FOR_BRANCHING],
                since=PLACEBO_MONTH_B,
                until=PLACEBO_MONTH_B,
                moves=MOVES_PER_QUERY,
            )
            placebo = {"month_a": moves_dict(data_a), "month_b": moves_dict(data_b)}

        nodes_out.append(
            {
                "path_uci": node.path_uci,
                "path_san": node.path_san,
                "systems": node.systems,
                "lichess": {
                    PRIMARY_SPEED: lichess_blitz,
                    **{s: {"discovery": v} for s, v in lichess_secondary.items()},
                },
                "masters": masters,
                "placebo": placebo,
            }
        )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rating_bands": RATING_BANDS,
        "primary_speed": PRIMARY_SPEED,
        "secondary_speeds": [] if args.skip_secondary_speeds else SECONDARY_SPEEDS,
        "windows": {
            "discovery": {"since": DISCOVERY_SINCE, "until": DISCOVERY_UNTIL},
            "validation": {"since": VALIDATION_SINCE, "until": VALIDATION_UNTIL},
        },
        "placebo_months": None
        if args.skip_placebo
        else {"month_a": PLACEBO_MONTH_A, "month_b": PLACEBO_MONTH_B},
        "reference_band_for_branching": REFERENCE_BAND_FOR_BRANCHING,
        "branch_factor": args.branch_factor,
        "min_popularity_share": args.min_share,
        "seeds": [{"system": s, "san": san, "extra_depth": d} for s, san, d in SEEDS_SAN],
        "nodes": nodes_out,
        "api_requests_made": client.requests_made,
        "cache_hits": client.cache_hits,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(
        f"Wrote {out_path} ({len(nodes_out)} nodes). "
        f"API requests this run: {client.requests_made}, cache hits: {client.cache_hits}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
