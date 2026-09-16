"""Placebo / null-calibration logic, split out of scripts/placebo_check.py
so it's unit-testable against synthetic fixtures with a known ground-truth
false-positive rate.

See scripts/placebo_check.py's module docstring for the full rationale:
briefly, this compares each move's score between two adjacent months
inside the discovery window (a near-null: no hypothesized reason for a
real difference) and checks whether the bootstrap test's raw p<alpha rate
matches the nominal alpha -- i.e. whether the pipeline's significance
tests are calibrated rather than systematically over- or under-confident.
"""

from __future__ import annotations

from .stats import MoveOutcome, benjamini_hochberg, bootstrap_score_difference, wilson_interval


def placebo_comparisons(
    nodes: list[dict], min_games: int, n_boot: int = 10000, seed_base: int = 0
) -> list[dict]:
    """Build the null-comparison family: for every position, every
    candidate move present in BOTH placebo sub-windows (with enough games
    in each to bother testing), bootstrap-compare its score between the
    two months."""
    comparisons = []
    for i, node in enumerate(nodes):
        placebo = node.get("placebo")
        if not placebo:
            continue
        month_a, month_b = placebo["month_a"], placebo["month_b"]
        for uci, a_d in month_a.items():
            b_d = month_b.get(uci)
            if not b_d:
                continue
            if a_d["total"] < min_games or b_d["total"] < min_games:
                continue
            a_out = MoveOutcome(label=a_d["san"], wins=a_d["wins"], draws=a_d["draws"], losses=a_d["losses"])
            b_out = MoveOutcome(label=b_d["san"], wins=b_d["wins"], draws=b_d["draws"], losses=b_d["losses"])
            boot = bootstrap_score_difference(a_out, b_out, n_boot=n_boot, seed=seed_base + i)
            if boot is None:
                continue
            comparisons.append(
                {
                    "path_san": node["path_san"],
                    "uci": uci,
                    "san": a_d["san"],
                    "month_a_n": a_d["total"],
                    "month_b_n": b_d["total"],
                    "observed_diff": boot.observed_diff,
                    "raw_p_value": boot.p_value,
                }
            )
    return comparisons


def calibration_summary(comparisons: list[dict], alpha: float = 0.05) -> dict:
    """Given a list of null comparisons (each with a raw_p_value), report
    the observed false-positive rate with a Wilson CI, whether the nominal
    alpha falls inside that CI (well-calibrated), and the same after BH
    correction (which should collapse toward ~0 under a true null)."""
    n = len(comparisons)
    if n == 0:
        return {
            "n_comparisons": 0,
            "raw_significant_count": 0,
            "raw_false_positive_rate": None,
            "raw_rate_95ci": None,
            "nominal_alpha_within_ci": None,
            "fdr_significant_count": 0,
            "fdr_false_positive_rate": None,
        }

    raw_sig = sum(1 for c in comparisons if c["raw_p_value"] < alpha)
    raw_rate = raw_sig / n
    ci_lo, ci_hi = wilson_interval(raw_rate, n)
    well_calibrated = ci_lo <= alpha <= ci_hi

    p_values = [c["raw_p_value"] for c in comparisons]
    reject, _adjusted = benjamini_hochberg(p_values, alpha=alpha)
    fdr_sig = sum(reject)

    return {
        "n_comparisons": n,
        "raw_significant_count": raw_sig,
        "raw_false_positive_rate": raw_rate,
        "raw_rate_95ci": [ci_lo, ci_hi],
        "nominal_alpha_within_ci": well_calibrated,
        "fdr_significant_count": fdr_sig,
        "fdr_false_positive_rate": fdr_sig / n,
    }
