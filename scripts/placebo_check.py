#!/usr/bin/env python3
"""Placebo / null-calibration adversarial check.

Compares each candidate move's score between two ADJACENT months squarely
inside the discovery window (2021-06 vs 2021-07 by default -- see
scripts/collect_data.py's PLACEBO_MONTH_A/B), at the reference rating band,
for every position in the tree. There is no hypothesized reason a move's
score should differ between two adjacent months of the same rating band
and speed pool, so this is as close to a true null as this dataset can
offer (the caveat -- chess "meta" can genuinely drift even month to month,
which would inflate the observed false-positive rate for a REAL reason
rather than a pipeline bug -- is discussed in the output and in
docs/findings.md).

If the statistical pipeline (bootstrap test + implicit independence/
variance assumptions) is well-calibrated, roughly alpha (5% by default) of
these null comparisons should come out "significant" at raw p < alpha
purely by chance. This script reports the actual observed rate, with a
Wilson confidence interval on it, and separately reports the rate after
BH correction (which should collapse toward ~0%, since under a true null
BH should reject almost nothing -- itself a sanity check on the FDR
implementation, distinct from testing raw-p calibration).

Core logic lives in opening_divergence.placebo (unit-tested there against
synthetic fixtures with a known ground-truth false-positive rate); this
script is just the I/O wrapper.

Usage:
    python scripts/placebo_check.py [--tree data/processed/opening_tree.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.placebo import calibration_summary, placebo_comparisons  # noqa: E402
from opening_divergence.stats import benjamini_hochberg  # noqa: E402

# Placebo comparisons use a much smaller n floor than MIN_SAMPLE_SIZE: a
# single month's data is inherently smaller than a multi-year window, and
# this check's purpose is calibration (does the TEST behave correctly),
# not making a "finding" that needs power to detect a specific effect size.
PLACEBO_MIN_GAMES_PER_SIDE = 200


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--json-out", default="data/processed/placebo_results.json")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=10000)
    parser.add_argument("--min-games", type=int, default=PLACEBO_MIN_GAMES_PER_SIDE)
    args = parser.parse_args()

    tree = json.load(open(args.tree, encoding="utf-8"))
    if not tree.get("placebo_months"):
        print("Tree was collected with --skip-placebo; nothing to check.", file=sys.stderr)
        return 1

    comparisons = placebo_comparisons(tree["nodes"], args.min_games, args.n_boot)
    if not comparisons:
        print("No placebo comparisons met the minimum-games threshold.", file=sys.stderr)
        return 1

    summary = calibration_summary(comparisons, alpha=args.alpha)

    p_values = [c["raw_p_value"] for c in comparisons]
    reject, adjusted = benjamini_hochberg(p_values, alpha=args.alpha)
    for c, adj, rej in zip(comparisons, adjusted, reject):
        c["fdr_adjusted_p_value"] = adj
        c["fdr_significant"] = rej

    output = {
        "placebo_months": tree["placebo_months"],
        "min_games_per_side": args.min_games,
        "alpha": args.alpha,
        **summary,
        "comparisons": sorted(comparisons, key=lambda c: c["raw_p_value"]),
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    n, raw_sig, raw_rate = (
        summary["n_comparisons"],
        summary["raw_significant_count"],
        summary["raw_false_positive_rate"],
    )
    ci_lo, ci_hi = summary["raw_rate_95ci"]
    well_calibrated = summary["nominal_alpha_within_ci"]
    fdr_sig, fdr_rate = summary["fdr_significant_count"], summary["fdr_false_positive_rate"]
    verdict = "WELL-CALIBRATED" if well_calibrated else "MISCALIBRATED -- investigate"

    print(
        f"{n} null (placebo) comparisons between {tree['placebo_months']['month_a']} and "
        f"{tree['placebo_months']['month_b']}.\n"
        f"Raw false-positive rate: {raw_sig}/{n} = {raw_rate * 100:.2f}% "
        f"(95% CI [{ci_lo * 100:.2f}%, {ci_hi * 100:.2f}%]); nominal alpha={args.alpha * 100:.0f}% is "
        f"{'inside' if well_calibrated else 'OUTSIDE'} that CI -> {verdict}.\n"
        f"After BH correction: {fdr_sig}/{n} = {fdr_rate * 100:.2f}% (expected: near 0% under a true null).\n"
        f"Wrote {out_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
