#!/usr/bin/env python3
"""Threshold-sensitivity adversarial check.

Every headline claim in this project depends on two somewhat-arbitrary
choices: the minimum-sample-size threshold (MIN_SAMPLE_SIZE, itself
derived from a power calculation -- see stats.py -- but still a choice of
target effect size/power) and which two rating bands count as "low" and
"high" when asking whether the best move shifts with rating (this project
uses the extremes, 1000 and 2500, by default). This script reruns the
discovery-window analysis across a grid of:

  - min-sample-size multiplier: 0.5x, 1x, 2x the power-derived default
  - rating-band span: extreme (1000 vs 2500, the default), inward-1
    (1200 vs 2200), inward-2 (1400 vs 2000) -- i.e. the API's own
    band boundaries pulled in one and two steps from each edge, since
    the bands themselves are fixed categorical buckets and can't be
    continuously perturbed

and reports, for the baseline run's headline (FDR-significant) findings,
how many of the 3x3=9 grid cells they remain FDR-significant in. A finding
that's significant at all 9 combinations is robust; one significant at
only 1-2 is fragile and should be flagged as such rather than presented
as equally solid.

Note: this grid's "baseline" cell (min_n multiplier=1x, extreme bands) is
its own self-contained rerun with rating_bands restricted to exactly the
two boundary bands in play at each grid cell -- it does NOT reuse
scripts/analyze_divergence.py's full 8-band discovery_findings.json
output, since popularity-gap findings there are checked at all 8 bands
individually. This keeps every one of the 9 cells apples-to-apples with
each other (same rating_bands scope varies only the two axes being
tested); see docs/findings.md for how its counts relate to the main run.

Usage:
    python scripts/sensitivity_check.py [--tree data/processed/opening_tree.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.divergence import build_finding_family  # noqa: E402
from opening_divergence.stats import MIN_SAMPLE_SIZE, benjamini_hochberg  # noqa: E402

MIN_N_MULTIPLIERS = [0.5, 1.0, 2.0]
BAND_SPANS = {
    "extreme (1000/2500)": [1000, 2500],
    "inward-1 (1200/2200)": [1200, 2200],
    "inward-2 (1400/2000)": [1400, 2000],
}


def run_grid_cell(nodes, rating_bands, min_n, speed, n_boot, alpha):
    findings = build_finding_family(nodes, rating_bands, min_n, speed, "discovery", n_boot=n_boot)
    p_values = [f.raw_p_value for f in findings]
    reject, _adjusted = benjamini_hochberg(p_values, alpha=alpha)
    significant_keys = {f.key() for f, rej in zip(findings, reject) if rej}
    return significant_keys, len(findings)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--json-out", default="data/processed/sensitivity_results.json")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--n-boot", type=int, default=4000, help="Lower default than other scripts: 9 grid cells."
    )
    args = parser.parse_args()

    tree = json.load(open(args.tree, encoding="utf-8"))
    nodes = tree["nodes"]
    speed = tree["primary_speed"]

    baseline_bands = [1000, 2500]
    baseline_min_n = MIN_SAMPLE_SIZE

    grid = {}
    print("Running 3x3 sensitivity grid (min-n multiplier x rating-band span)...", file=sys.stderr)
    for mult in MIN_N_MULTIPLIERS:
        min_n = max(2, round(MIN_SAMPLE_SIZE * mult))
        for span_label, bands in BAND_SPANS.items():
            cell_key = f"min_n_x{mult}={min_n} | {span_label}"
            keys, n_findings = run_grid_cell(nodes, bands, min_n, speed, args.n_boot, args.alpha)
            grid[cell_key] = {
                "min_n": min_n,
                "band_span": span_label,
                "n_comparisons": n_findings,
                "n_significant": len(keys),
            }
            grid[cell_key]["_keys"] = keys
            print(f"  {cell_key}: {len(keys)}/{n_findings} FDR-significant", file=sys.stderr)

    baseline_cell_key = f"min_n_x1.0={baseline_min_n} | extreme (1000/2500)"
    baseline_keys = grid[baseline_cell_key]["_keys"]

    stability = []
    for key in sorted(baseline_keys, key=str):
        n_cells_significant = sum(1 for cell in grid.values() if key in cell["_keys"])
        kind, path_uci, speed_, band_a, band_b, a_uci, b_uci = key
        stability.append(
            {
                "kind": kind,
                "path_uci": list(path_uci),
                "band_a": band_a,
                "band_b": band_b,
                "a_uci": a_uci,
                "b_uci": b_uci,
                "n_grid_cells_significant_out_of_9": n_cells_significant,
                "robust": n_cells_significant == 9,
            }
        )
    stability.sort(key=lambda s: s["n_grid_cells_significant_out_of_9"])

    n_robust = sum(1 for s in stability if s["robust"])
    n_fragile = len(stability) - n_robust

    grid_out = {k: {kk: vv for kk, vv in v.items() if kk != "_keys"} for k, v in grid.items()}
    output = {
        "baseline_min_sample_size": baseline_min_n,
        "baseline_bands": baseline_bands,
        "min_n_multipliers": MIN_N_MULTIPLIERS,
        "band_spans": BAND_SPANS,
        "grid": grid_out,
        "n_baseline_headline_findings": len(baseline_keys),
        "n_robust_across_all_9_cells": n_robust,
        "n_fragile": n_fragile,
        "stability": stability,
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(
        f"\nBaseline (min_n={baseline_min_n}, bands=1000/2500): {len(baseline_keys)} headline findings.\n"
        f"Robust (significant in all 9 grid cells): {n_robust}\n"
        f"Fragile (significant in baseline but not all cells): {n_fragile}\n"
        f"Wrote {out_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
