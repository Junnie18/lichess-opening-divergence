#!/usr/bin/env python3
"""Discovery-window divergence analysis: builds the full family of
"is move A better than move B" comparisons (best-move shifts across rating
bands, popular-vs-better-move gaps, masters-vs-Lichess-pool divergence),
computes a bootstrap p-value for every one of them, and applies a SINGLE
Benjamini-Hochberg FDR correction across the entire family (see
opening_divergence.stats.benjamini_hochberg for why: running hundreds of
comparisons at raw alpha=0.05 guarantees a fistful of false positives even
under a true null everywhere).

This script ONLY looks at the discovery window. Findings that survive FDR
correction here are candidates for two further checks that live in their
own scripts (kept separate because they use different data / a different
family of tests, not because they're less important):

    scripts/validate_findings.py   -- out-of-sample replication in the
                                       validation window (the centerpiece
                                       check)
    scripts/cross_speed_check.py   -- does it hold in rapid/classical too?

Usage:
    python scripts/analyze_divergence.py \
        [--tree data/processed/opening_tree.json] \
        [--json-out data/processed/discovery_findings.json] \
        [--min-games N]  # default: power-calculation-derived MIN_SAMPLE_SIZE
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opening_divergence.divergence import build_finding_family  # noqa: E402
from opening_divergence.stats import MIN_SAMPLE_SIZE, benjamini_hochberg  # noqa: E402


def finding_to_dict(f, adjusted_p: float, fdr_significant: bool) -> dict:
    return {
        "kind": f.kind,
        "path_san": f.path_san,
        "path_uci": f.path_uci,
        "speed": f.speed,
        "window": f.window,
        "band_a": f.band_a,
        "band_b": f.band_b,
        "a_uci": f.a_uci,
        "a": f.a,
        "b_uci": f.b_uci,
        "b": f.b,
        "observed_diff": f.bootstrap.observed_diff,
        "ci_lo": f.bootstrap.ci_lo,
        "ci_hi": f.bootstrap.ci_hi,
        "raw_p_value": f.raw_p_value,
        "fdr_adjusted_p_value": adjusted_p,
        "raw_significant": f.raw_p_value < 0.05,
        "fdr_significant": fdr_significant,
        "detail": f.detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tree", default="data/processed/opening_tree.json")
    parser.add_argument("--json-out", default="data/processed/discovery_findings.json")
    parser.add_argument("--min-games", type=int, default=MIN_SAMPLE_SIZE)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=10000)
    args = parser.parse_args()

    tree_path = Path(args.tree)
    if not tree_path.exists():
        print(f"{tree_path} not found. Run scripts/collect_data.py first.", file=sys.stderr)
        return 1

    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)

    speed = tree["primary_speed"]
    rating_bands = tree["rating_bands"]
    nodes = tree["nodes"]

    print(
        f"Building discovery-window finding family over {len(nodes)} positions, "
        f"speed={speed}, min_games={args.min_games}...",
        file=sys.stderr,
    )
    findings = build_finding_family(
        nodes, rating_bands, args.min_games, speed, "discovery", n_boot=args.n_boot
    )
    print(f"{len(findings)} raw comparisons found.", file=sys.stderr)

    p_values = [f.raw_p_value for f in findings]
    reject, adjusted = benjamini_hochberg(p_values, alpha=args.alpha)

    findings_out = [finding_to_dict(f, adj, rej) for f, adj, rej in zip(findings, adjusted, reject)]
    findings_out.sort(key=lambda d: d["fdr_adjusted_p_value"])

    n_raw_sig = sum(1 for d in findings_out if d["raw_significant"])
    n_fdr_sig = sum(reject)
    by_kind = {}
    for d in findings_out:
        by_kind.setdefault(d["kind"], {"total": 0, "raw_sig": 0, "fdr_sig": 0})
        by_kind[d["kind"]]["total"] += 1
        by_kind[d["kind"]]["raw_sig"] += d["raw_significant"]
        by_kind[d["kind"]]["fdr_sig"] += d["fdr_significant"]

    output = {
        "tree_generated_at": tree["generated_at"],
        "speed": speed,
        "window": "discovery",
        "discovery_range": tree["windows"]["discovery"],
        "rating_bands": rating_bands,
        "min_sample_size": args.min_games,
        "alpha": args.alpha,
        "n_boot": args.n_boot,
        "nodes_analyzed": len(nodes),
        "total_comparisons": len(findings_out),
        "raw_significant_count": n_raw_sig,
        "fdr_significant_count": n_fdr_sig,
        "by_kind": by_kind,
        "findings": findings_out,
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(
        f"{len(findings_out)} comparisons: {n_raw_sig} raw-significant (p<{args.alpha}), "
        f"{n_fdr_sig} FDR-significant after BH correction ({n_raw_sig - n_fdr_sig} raw-significant "
        f"findings did NOT survive multiple-comparisons correction).\n"
        f"By kind: {json.dumps(by_kind)}\n"
        f"Wrote {out_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
