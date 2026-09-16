#!/usr/bin/env python3
"""Cross-speed replication check: do headline (FDR-significant, blitz,
discovery-window) findings hold in rapid and classical time controls too,
or are they blitz-specific?

Unlike scripts/validate_findings.py (a different TIME period, same speed),
this re-tests the same comparison in the same discovery time period but a
DIFFERENT speed (rapid/classical instead of blitz) -- both collected
discovery-window-only (see scripts/collect_data.py). A "speed-consistent"
finding replicates in the sense used by validate_findings.py: direction
matches, raw p < alpha, and it survives its own BH correction applied
across just this retest family.

This is a same-window, different-population check -- it answers "is this
a blitz-only phenomenon?", a different (and, per the project brief,
equally mandatory) question from "did it hold up over time?".

Usage:
    python scripts/cross_speed_check.py \
        [--tree data/processed/opening_tree.json] \
        [--discovery-findings data/processed/discovery_findings.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.stats import benjamini_hochberg, bootstrap_score_difference  # noqa: E402
from opening_divergence.validate import build_node_index, outcome_from_band_dict  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--discovery-findings", default="data/processed/discovery_findings.json")
    parser.add_argument("--json-out", default="data/processed/cross_speed_results.json")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=10000)
    args = parser.parse_args()

    tree = json.load(open(args.tree, encoding="utf-8"))
    discovery = json.load(open(args.discovery_findings, encoding="utf-8"))
    secondary_speeds = tree.get("secondary_speeds") or []
    if not secondary_speeds:
        print("Tree was collected with --skip-secondary-speeds; nothing to check.", file=sys.stderr)
        return 1

    node_index = build_node_index(tree["nodes"])
    headline = [f for f in discovery["findings"] if f["fdr_significant"]]
    print(
        f"Re-testing {len(headline)} headline findings across speeds {secondary_speeds}...", file=sys.stderr
    )

    results_by_speed = {}
    for speed in secondary_speeds:
        results = []
        for f in headline:
            node = node_index.get(tuple(f["path_uci"]))
            untestable_reason = None
            boot = None
            a_out = b_out = None
            if node is None:
                untestable_reason = "position missing from tree"
            else:
                a_out = outcome_from_band_dict(node, speed, "discovery", f["band_a"], f["a_uci"])
                b_out = outcome_from_band_dict(node, speed, "discovery", f["band_b"], f["b_uci"])
                if a_out is None or b_out is None:
                    untestable_reason = f"move not present in {speed} data at this band"
                elif a_out.total == 0 or b_out.total == 0:
                    untestable_reason = f"zero games for one side in {speed}"
                else:
                    boot = bootstrap_score_difference(a_out, b_out, n_boot=args.n_boot, seed=0)

            entry = {
                "kind": f["kind"],
                "path_san": f["path_san"],
                "band_a": f["band_a"],
                "band_b": f["band_b"],
                "a_uci": f["a_uci"],
                "b_uci": f["b_uci"],
                "blitz_observed_diff": f["observed_diff"],
                "untestable_reason": untestable_reason,
            }
            if boot is not None:
                entry[f"{speed}_observed_diff"] = boot.observed_diff
                entry[f"{speed}_raw_p_value"] = boot.p_value
                entry["direction_matches"] = (boot.observed_diff > 0) == (f["observed_diff"] > 0)
                entry[f"{speed}_a_n"] = a_out.total
                entry[f"{speed}_b_n"] = b_out.total
            results.append(entry)

        testable = [r for r in results if r["untestable_reason"] is None]
        p_values = [r[f"{speed}_raw_p_value"] for r in testable]
        reject, adjusted = benjamini_hochberg(p_values, alpha=args.alpha)
        for r, adj, rej in zip(testable, adjusted, reject):
            r[f"{speed}_fdr_adjusted_p"] = adj
            r["replicated"] = bool(r["direction_matches"] and rej)

        n_replicated = sum(1 for r in testable if r["replicated"])
        results_by_speed[speed] = {
            "n_headline": len(headline),
            "n_testable": len(testable),
            "n_replicated": n_replicated,
            "replication_rate": (n_replicated / len(testable)) if testable else None,
            "results": results,
        }
        rate = results_by_speed[speed]["replication_rate"]
        rate_str = f"{rate * 100:.1f}%" if rate is not None else "n/a"
        print(f"  {speed}: {n_replicated}/{len(testable)} replicated ({rate_str})", file=sys.stderr)

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results_by_speed, f, indent=2)
    print(f"Wrote {out_path}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
