import numpy as np

from opening_divergence.placebo import calibration_summary, placebo_comparisons


def _move_dict(san, wins, draws, losses):
    total = wins + draws + losses
    return {"san": san, "wins": wins, "draws": draws, "losses": losses, "total": total}


def test_placebo_comparisons_skips_positions_without_placebo_data():
    nodes = [{"path_san": "x", "placebo": None}]
    assert placebo_comparisons(nodes, min_games=200) == []


def test_placebo_comparisons_skips_moves_below_min_games():
    nodes = [
        {
            "path_san": "1. e4",
            "placebo": {
                "month_a": {"e2e4": _move_dict("e4", 50, 30, 20)},  # n=100, below 200 floor
                "month_b": {"e2e4": _move_dict("e4", 55, 25, 20)},
            },
        }
    ]
    assert placebo_comparisons(nodes, min_games=200) == []


def test_placebo_comparisons_skips_moves_missing_from_either_month():
    nodes = [
        {
            "path_san": "1. e4",
            "placebo": {
                "month_a": {"e2e4": _move_dict("e4", 300, 200, 200)},
                "month_b": {"d2d4": _move_dict("d4", 300, 200, 200)},  # different move only
            },
        }
    ]
    assert placebo_comparisons(nodes, min_games=200) == []


def test_placebo_comparisons_builds_one_entry_per_shared_move():
    nodes = [
        {
            "path_san": "1. e4",
            "placebo": {
                "month_a": {
                    "e2e4": _move_dict("e4", 300, 200, 200),
                    "d2d4": _move_dict("d4", 250, 250, 200),
                },
                "month_b": {
                    "e2e4": _move_dict("e4", 310, 190, 200),
                    "d2d4": _move_dict("d4", 240, 260, 200),
                },
            },
        }
    ]
    comparisons = placebo_comparisons(nodes, min_games=200, n_boot=500)
    assert len(comparisons) == 2
    assert {c["uci"] for c in comparisons} == {"e2e4", "d2d4"}
    for c in comparisons:
        assert 0.0 <= c["raw_p_value"] <= 1.0


def test_calibration_summary_empty_input():
    summary = calibration_summary([])
    assert summary["n_comparisons"] == 0
    assert summary["raw_false_positive_rate"] is None


def test_calibration_summary_well_calibrated_when_p_values_are_truly_uniform():
    # Simulate a perfectly calibrated test: under a true null, p-values are
    # Uniform(0,1) by construction. The observed rate of p < 0.05 should be
    # close to 5%, and calibration_summary should recognize the nominal
    # alpha falls inside the Wilson CI around the observed rate.
    rng = np.random.default_rng(0)
    p_values = rng.uniform(0, 1, size=2000)
    comparisons = [{"raw_p_value": float(p)} for p in p_values]
    summary = calibration_summary(comparisons, alpha=0.05)
    assert summary["n_comparisons"] == 2000
    assert 0.03 < summary["raw_false_positive_rate"] < 0.08
    assert summary["nominal_alpha_within_ci"] is True
    # Under a true null, BH correction should reject far fewer than raw.
    assert summary["fdr_significant_count"] < summary["raw_significant_count"]


def test_calibration_summary_flags_miscalibration_when_false_positive_rate_is_way_off():
    # Simulate a badly miscalibrated test: p-values skewed toward 0 (as if
    # independence/variance assumptions were wrong and the test were
    # systematically over-confident) -- calibration_summary should flag
    # this as nominal alpha NOT within the observed CI.
    rng = np.random.default_rng(1)
    p_values = rng.beta(0.3, 3.0, size=2000)  # heavily skewed toward 0
    comparisons = [{"raw_p_value": float(p)} for p in p_values]
    summary = calibration_summary(comparisons, alpha=0.05)
    assert summary["raw_false_positive_rate"] > 0.15
    assert summary["nominal_alpha_within_ci"] is False


def test_calibration_summary_ci_narrows_and_centers_on_observed_rate():
    comparisons = [{"raw_p_value": 0.01} for _ in range(50)] + [{"raw_p_value": 0.5} for _ in range(950)]
    summary = calibration_summary(comparisons, alpha=0.05)
    assert summary["raw_significant_count"] == 50
    assert abs(summary["raw_false_positive_rate"] - 0.05) < 1e-9
    ci_lo, ci_hi = summary["raw_rate_95ci"]
    assert ci_lo < 0.05 < ci_hi
