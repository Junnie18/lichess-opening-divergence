#!/usr/bin/env python3
"""Divergence analysis over the opening tree collected by collect_data.py.

For every tree node (a position reached by a specific move sequence),
compares the empirical score (White's expected points per game) of each
candidate reply across rating bands, and flags:

  1. Positions where the *confidently-best* move (score-ranked, subject to
     --min-games) differs between the lowest and highest rating band with
     enough data -- "does the best move change with rating?"
  2. Positions where the *most popular* move in a band is not the
     best-scoring one, and the gap is large enough to be statistically
     significant -- "book move that underperforms."
  3. Positions where the masters' most-played move's score at the lowest
     Lichess band diverges sharply from its score at the highest band --
     "does master theory hold up in the lower-rated pool?"

Writes a JSON of all findings plus a generated Markdown report with
concrete tables (used as the data backing docs/findings.md).

Usage:
    python scripts/analyze_divergence.py \
        [--tree data/processed/opening_tree.json] \
        [--json-out data/processed/divergence_findings.json] \
        [--md-out docs/findings_generated.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.divergence import (  # noqa: E402
    analyze_best_move_shift,
    analyze_master_theory,
    analyze_popularity_gap,
    render_markdown,
)
from opening_divergence.stats import MIN_SAMPLE_SIZE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--json-out", default="data/processed/divergence_findings.json")
    parser.add_argument("--md-out", default="docs/findings_generated.md")
    parser.add_argument("--min-games", type=int, default=MIN_SAMPLE_SIZE)
    args = parser.parse_args()

    tree_path = Path(args.tree)
    if not tree_path.exists():
        print(
            f"{tree_path} not found. Run scripts/collect_data.py first "
            "(requires LICHESS_TOKEN -- see README).",
            file=sys.stderr,
        )
        return 1

    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)

    speed = tree["primary_speed"]
    rating_bands = tree["rating_bands"]
    nodes = tree["nodes"][speed]

    best_move_shifts = []
    popularity_gaps = []
    master_theory = []
    for node in nodes:
        shift = analyze_best_move_shift(node, rating_bands, args.min_games)
        if shift:
            best_move_shifts.append(shift)
        popularity_gaps.extend(analyze_popularity_gap(node, rating_bands, args.min_games))
        theory = analyze_master_theory(node, rating_bands, args.min_games)
        if theory:
            master_theory.append(theory)

    findings = {
        "tree_generated_at": tree["generated_at"],
        "speed": speed,
        "rating_bands": rating_bands,
        "min_sample_size": args.min_games,
        "nodes_analyzed": len(nodes),
        "best_move_shifts": best_move_shifts,
        "popularity_gaps": popularity_gaps,
        "master_theory": master_theory,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)

    md_out = Path(args.md_out)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(findings), encoding="utf-8")

    print(
        f"Analyzed {len(nodes)} nodes: {len(best_move_shifts)} best-move shifts, "
        f"{len(popularity_gaps)} popularity gaps, {len(master_theory)} master-theory comparisons.\n"
        f"Wrote {json_out} and {md_out}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
