#!/usr/bin/env python3
"""Out-of-sample validation -- THE centerpiece rigor check for this project.

Takes every FDR-significant discovery-window finding from
scripts/analyze_divergence.py and re-tests the *exact same* comparison
(same position, same speed, same bands, same pair of moves) against
validation-window data (2023-01 onward, strictly after the discovery
window ends 2022-12 -- see scripts/collect_data.py). A finding "replicates"
if, in the validation window:

  1. the sign of the score difference matches discovery (same move still
     ahead), AND
  2. it's significant at raw p < alpha, AND
  3. it survives its OWN Benjamini-Hochberg correction applied across just
     this validation retest family (a separate, smaller family from the
     original discovery-wide correction -- retesting N specific claims is
     its own multiple-comparisons problem).

Reports the replication rate honestly, broken out by finding kind, and
lists every finding that did NOT replicate (direction flip, no longer
significant, or no validation-window data at all) rather than only
showing the successes.

Usage:
    python scripts/validate_findings.py \
        [--tree data/processed/opening_tree.json] \
        [--discovery-findings data/processed/discovery_findings.json] \
        [--json-out data/processed/validation_results.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.stats import MoveOutcome, benjamini_hochberg, bootstrap_score_difference  # noqa: E402


def build_node_index(nodes: list[dict]) -> dict[tuple, dict]:
    return {tuple(n["path_uci"]): n for n in nodes}


def outcome_from_band_dict(node: dict, speed: str, window: str, band: str, uci: str) -> MoveOutcome | None:
    d = node.get("lichess", {}).get(speed, {}).get(window, {}).get(band, {}).get(uci)
    if d is None:
        return None
    return MoveOutcome(label=d["san"], wins=d["wins"], draws=d["draws"], losses=d["losses"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--discovery-findings", default="data/processed/discovery_findings.json")
    parser.add_argument("--json-out", default="data/processed/validation_results.json")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=10000)
    parser.add_argument(
        "--headline-only",
        action="store_true",
        default=True,
        help="Only re-test FDR-significant discovery findings (the default and recommended mode).",
    )
    args = parser.parse_args()

    tree = json.load(open(args.tree, encoding="utf-8"))
    discovery = json.load(open(args.discovery_findings, encoding="utf-8"))

    node_index = build_node_index(tree["nodes"])
    headline = [f for f in discovery["findings"] if f["fdr_significant"]]
    print(
        f"Re-testing {len(headline)} FDR-significant discovery findings against validation-window data...",
        file=sys.stderr,
    )

    results = []
    for f in headline:
        node = node_index.get(tuple(f["path_uci"]))
        untestable_reason = None
        boot = None
        if node is None:
            untestable_reason = "position missing from tree"
        else:
            a_out = outcome_from_band_dict(node, f["speed"], "validation", f["band_a"], f["a_uci"])
            b_out = outcome_from_band_dict(node, f["speed"], "validation", f["band_b"], f["b_uci"])
            if a_out is None or b_out is None:
                untestable_reason = "move not present in validation-window data at this band"
            elif a_out.total == 0 or b_out.total == 0:
                untestable_reason = "zero games for one side in validation window"
            else:
                boot = bootstrap_score_difference(a_out, b_out, n_boot=args.n_boot, seed=0)

        entry = {
            "kind": f["kind"],
            "path_san": f["path_san"],
            "speed": f["speed"],
            "band_a": f["band_a"],
            "band_b": f["band_b"],
            "a_uci": f["a_uci"],
            "b_uci": f["b_uci"],
            "discovery_observed_diff": f["observed_diff"],
            "discovery_fdr_adjusted_p": f["fdr_adjusted_p_value"],
            "untestable_reason": untestable_reason,
        }
        if boot is not None:
            entry["validation_observed_diff"] = boot.observed_diff
            entry["validation_ci_lo"] = boot.ci_lo
            entry["validation_ci_hi"] = boot.ci_hi
            entry["validation_raw_p_value"] = boot.p_value
            entry["direction_matches"] = (boot.observed_diff > 0) == (f["observed_diff"] > 0)
            entry["validation_a_n"] = a_out.total
            entry["validation_b_n"] = b_out.total
        results.append(entry)

    testable = [r for r in results if r["untestable_reason"] is None]
    p_values = [r["validation_raw_p_value"] for r in testable]
    reject, adjusted = benjamini_hochberg(p_values, alpha=args.alpha)
    for r, adj, rej in zip(testable, adjusted, reject):
        r["validation_fdr_adjusted_p"] = adj
        r["replicated"] = bool(r["direction_matches"] and rej)

    n_headline = len(headline)
    n_testable = len(testable)
    n_replicated = sum(1 for r in testable if r["replicated"])
    n_direction_only = sum(1 for r in testable if r["direction_matches"] and not r["replicated"])
    n_direction_flip = sum(1 for r in testable if not r["direction_matches"])
    n_untestable = n_headline - n_testable

    by_kind = {}
    for r in results:
        by_kind.setdefault(r["kind"], {"headline": 0, "testable": 0, "replicated": 0})
        by_kind[r["kind"]]["headline"] += 1
        if r["untestable_reason"] is None:
            by_kind[r["kind"]]["testable"] += 1
            by_kind[r["kind"]]["replicated"] += r.get("replicated", False)

    replication_rate = (n_replicated / n_testable) if n_testable else None

    output = {
        "discovery_window": discovery.get("discovery_range"),
        "validation_window": tree["windows"]["validation"],
        "alpha": args.alpha,
        "n_headline_discovery_findings": n_headline,
        "n_testable": n_testable,
        "n_untestable": n_untestable,
        "n_replicated": n_replicated,
        "n_direction_matches_but_not_significant": n_direction_only,
        "n_direction_flipped": n_direction_flip,
        "replication_rate": replication_rate,
        "by_kind": by_kind,
        "results": sorted(
            results, key=lambda r: (r.get("untestable_reason") is not None, r["discovery_fdr_adjusted_p"])
        ),
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    rate_str = f"{replication_rate * 100:.1f}%" if replication_rate is not None else "n/a"
    print(
        f"{n_headline} headline discovery findings -> {n_testable} testable in validation window "
        f"({n_untestable} untestable: no/insufficient validation-window data).\n"
        f"Replication: {n_replicated}/{n_testable} = {rate_str}",
        file=sys.stderr,
    )
    print(
        f"  direction matched but lost significance: {n_direction_only}\n"
        f"  direction flipped: {n_direction_flip}\n"
        f"By kind: {json.dumps(by_kind)}\n"
        f"Wrote {out_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
