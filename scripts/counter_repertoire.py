#!/usr/bin/env python3
"""Counter-repertoire finder: given a target rating and an opponent's
opening, find the empirically best reply at that rating band.

The "score" of a candidate reply already reflects everything that happened
in every game that played it (it's an aggregate of real outcomes, not a
static one-ply evaluation), so ranking by score is inherently "a few plies
deep" -- it is not just judging the immediate position. Sample-size
confidence is enforced (src/opening_divergence/stats.py): moves with fewer
than --min-games games are flagged and, by default, hidden from the "best"
ranking (a 5-game 100% score is not a real signal).

Example:
    python scripts/counter_repertoire.py --rating 1400 --against "1. e4 e5"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.client import ExplorerAuthError, ExplorerClient, ExplorerError  # noqa: E402
from opening_divergence.notation import parse_move_text, uci_list_to_san_line  # noqa: E402
from opening_divergence.repertoire import (  # noqa: E402
    RATING_BAND_BOUNDARIES,
    nearest_band,
    own_score,
    rank_candidates,
)
from opening_divergence.stats import MIN_SAMPLE_SIZE, is_significantly_different  # noqa: E402
from opening_divergence.tree import candidates_from_response  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--rating", type=int, required=True, help="Target rating, e.g. 1400.")
    parser.add_argument(
        "--against", type=str, required=True, help='Opponent opening in SAN, e.g. "1. e4 e5".'
    )
    parser.add_argument(
        "--speed",
        default="blitz",
        choices=["bullet", "blitz", "rapid", "classical", "correspondence"],
    )
    parser.add_argument("--top", type=int, default=5, help="Number of candidate replies to show.")
    parser.add_argument(
        "--min-games",
        type=int,
        default=MIN_SAMPLE_SIZE,
        help=f"Minimum sample size to trust a move's win rate (default {MIN_SAMPLE_SIZE}).",
    )
    parser.add_argument("--cache-dir", default="data/raw")
    args = parser.parse_args()

    band = nearest_band(args.rating)
    if band != args.rating:
        print(
            f"Note: {args.rating} isn't an explorer rating-band boundary; using the {band}+ "
            f"band (boundaries: {RATING_BAND_BOUNDARIES[1:]}, each running up to the next).\n",
            file=sys.stderr,
        )

    try:
        uci_moves = parse_move_text(args.against)
    except ValueError as e:
        print(f"Could not parse --against '{args.against}': {e}", file=sys.stderr)
        return 2

    mover_is_white = len(uci_moves) % 2 == 0
    to_move = "White" if mover_is_white else "Black"

    client = ExplorerClient(cache_dir=args.cache_dir)
    try:
        data = client.lichess(play=",".join(uci_moves), speeds=[args.speed], ratings=[band], moves=12)
    except ExplorerAuthError as e:
        print(str(e), file=sys.stderr)
        return 1
    except ExplorerError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1

    candidates = rank_candidates(candidates_from_response(data), mover_is_white)
    if not candidates:
        print(
            f"No games found for this position in the {band}+ / {args.speed} bucket -- "
            "try a lower rating band, a different speed, or a shorter opening."
        )
        return 0

    confident = [c for c in candidates if c.outcome.total >= args.min_games]
    unconfident = [c for c in candidates if c.outcome.total < args.min_games]

    print(
        f"Against {uci_list_to_san_line(uci_moves)} ({to_move} to move), "
        f"{band}+ rated {args.speed} games:\n"
    )

    if not confident:
        print(
            f"No candidate reply has >= {args.min_games} games in this sample -- sample "
            "sizes are too small here to trust any win rate. Showing raw counts anyway, "
            "but treat every number below as unreliable:\n"
        )
        shown = candidates[: args.top]
    else:
        shown = confident[: args.top]

    for i, c in enumerate(shown, start=1):
        s = own_score(c, mover_is_white)
        flag = "" if c.outcome.total >= args.min_games else "  [LOW SAMPLE -- do not trust]"
        print(
            f"{i}. {c.san:8s} score={s:.3f}  n={c.outcome.total:6d}  "
            f"(W{c.outcome.wins}/D{c.outcome.draws}/L{c.outcome.losses}){flag}"
        )

    if (
        len(shown) >= 2
        and shown[0].outcome.total >= args.min_games
        and shown[1].outcome.total >= args.min_games
        and not is_significantly_different(shown[0].outcome, shown[1].outcome)
    ):
        print(
            f"\nNote: #1 ({shown[0].san}) and #2 ({shown[1].san}) are not statistically "
            "distinguishable at this sample size -- treat them as roughly tied, not "
            "'#1 is the answer'."
        )

    if unconfident:
        print(
            f"\n({len(unconfident)} more candidate move(s) omitted for having fewer than "
            f"{args.min_games} games -- pass --min-games to lower the bar if you want to see them.)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
