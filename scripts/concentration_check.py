#!/usr/bin/env python3
"""Outlier/concentration adversarial check for headline counter-repertoire
recommendations.

For every FDR-significant "popularity_gap" finding (popular move X
underperforms less-popular move Y at some band), fetches ONE extra live
query -- the position one ply after playing Y -- and computes the
Herfindahl-Hirschman Index (opening_divergence.concentration) over the
opponent's replies there. A high HHI means Y's good score is driven almost
entirely by opponents replying one specific way (a narrow trap, fragile if
the opponent knows better); a low HHI means Y performs well across a
broad spread of opponent replies (a robust recommendation).

Uses the SAME cached, rate-limited client as collect_data.py -- if the
child position happens to already be a tree node (common: a popular-enough
reply is often already BFS-expanded), this is a free cache hit; otherwise
it's one new request per finding, negligible next to the main collection.

Usage:
    python scripts/concentration_check.py \
        [--tree data/processed/opening_tree.json] \
        [--discovery-findings data/processed/discovery_findings.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.client import ExplorerClient  # noqa: E402
from opening_divergence.concentration import (  # noqa: E402
    dominant_share,
    herfindahl_index,
    is_concentration_risk,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--discovery-findings", default="data/processed/discovery_findings.json")
    parser.add_argument("--json-out", default="data/processed/concentration_results.json")
    parser.add_argument("--cache-dir", default="data/raw")
    args = parser.parse_args()

    tree = json.load(open(args.tree, encoding="utf-8"))
    discovery = json.load(open(args.discovery_findings, encoding="utf-8"))
    since, until = tree["windows"]["discovery"]["since"], tree["windows"]["discovery"]["until"]

    headline = [f for f in discovery["findings"] if f["fdr_significant"] and f["kind"] == "popularity_gap"]
    print(f"Checking concentration for {len(headline)} headline popularity-gap findings...", file=sys.stderr)

    client = ExplorerClient(cache_dir=args.cache_dir)
    results = []
    for f in headline:
        child_path = f["path_uci"] + [f["a_uci"]]  # a_uci is the recommended ("better") move
        data = client.lichess(
            play=",".join(child_path),
            speeds=[f["speed"]],
            ratings=[int(f["band_a"])],
            since=since,
            until=until,
            moves=12,
        )
        counts = [m["white"] + m["draws"] + m["black"] for m in data.get("moves", [])]
        hhi = herfindahl_index(counts)
        results.append(
            {
                "path_san": f["path_san"],
                "recommended_move": f["a"]["san"],
                "band": f["band_a"],
                "speed": f["speed"],
                "n_opponent_replies_seen": len(counts),
                "n_games_at_child_position": sum(counts),
                "herfindahl_index": hhi,
                "dominant_reply_share": dominant_share(counts),
                "concentration_risk": is_concentration_risk(hhi),
            }
        )

    n_risk = sum(1 for r in results if r["concentration_risk"])
    output = {
        "n_headline_recommendations_checked": len(results),
        "n_concentration_risk": n_risk,
        "n_broad_based": len(results) - n_risk,
        "results": sorted(results, key=lambda r: -(r["herfindahl_index"] or 0)),
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(
        f"{len(results)} recommendations checked: {n_risk} flagged as concentration risk "
        f"(HHI > threshold, i.e. one opponent reply dominates), {len(results) - n_risk} broad-based.\n"
        f"Wrote {out_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
