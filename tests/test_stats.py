import math

from opening_divergence.stats import (
    MIN_SAMPLE_SIZE,
    MoveOutcome,
    benjamini_hochberg,
    bootstrap_score_difference,
    compare_moves,
    confident_ranking,
    is_significantly_different,
    required_sample_size_per_group,
    score_confidence_interval,
    score_variance,
    wilson_interval,
)


def test_win_rate_and_score():
    o = MoveOutcome(label="e4", wins=50, draws=30, losses=20)
    assert o.total == 100
    assert o.win_rate == 0.5
    assert o.score == 0.5 + 0.15  # (50 + 15) / 100


def test_score_none_when_no_games():
    o = MoveOutcome(label="x", wins=0, draws=0, losses=0)
    assert o.total == 0
    assert o.win_rate is None
    assert o.score is None
    assert score_confidence_interval(o) is None
    assert score_variance(o) is None


def test_low_confidence_flag_uses_power_derived_threshold():
    # MIN_SAMPLE_SIZE is now derived from a power calculation (~2453 for
    # the default 4pp effect size / 80% power / alpha=0.05), not a round
    # number -- see stats.py's derivation. A sample of 1000 games, which
    # would have passed the old hardcoded threshold of 30, is still
    # correctly flagged low-confidence under the rigorous threshold.
    small = MoveOutcome(label="rare", wins=2, draws=1, losses=1)
    medium = MoveOutcome(label="medium", wins=500, draws=300, losses=200)  # n=1000
    huge = MoveOutcome(label="huge", wins=5000, draws=3000, losses=2000)  # n=10000
    assert small.low_confidence
    assert medium.low_confidence
    assert not huge.low_confidence


def test_required_sample_size_matches_hand_calculation():
    # n = 2 * (z_alpha/2 + z_power)^2 * sigma^2 / delta^2
    # For delta=0.04, alpha=0.05, power=0.80, sigma^2=0.25:
    # z_alpha/2 = 1.959964, z_power = 0.841621
    # n = 2 * (2.801585)^2 * 0.25 / 0.0016 = 2452.75... -> ceil = 2453
    assert required_sample_size_per_group(0.04, 0.05, 0.80, 0.25) == 2453
    assert MIN_SAMPLE_SIZE == 2453
    # Smaller target effect size -> need (much) more games; larger -> fewer.
    assert required_sample_size_per_group(0.02) > required_sample_size_per_group(0.04)
    assert required_sample_size_per_group(0.08) < required_sample_size_per_group(0.04)


def test_wilson_interval_contains_point_estimate_and_narrows_with_n():
    lo_small, hi_small = wilson_interval(0.5, 20)
    lo_big, hi_big = wilson_interval(0.5, 20000)
    assert lo_small <= 0.5 <= hi_small
    assert lo_big <= 0.5 <= hi_big
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_score_confidence_interval_hand_computed():
    # wins=50, draws=30, losses=20, n=100 -> score=0.65
    # p_win=0.5, p_draw=0.3, p_loss=0.2
    # per-game variance = 0.5*(1-0.65)^2 + 0.3*(0.5-0.65)^2 + 0.2*(0-0.65)^2
    #                    = 0.5*0.1225 + 0.3*0.0225 + 0.2*0.4225
    #                    = 0.06125 + 0.00675 + 0.0845 = 0.1525
    # SE = sqrt(0.1525 / 100) = sqrt(0.001525) = 0.039051248...
    # CI = 0.65 +/- 1.959964 * 0.039051248 = 0.65 +/- 0.0765374...
    o = MoveOutcome(label="x", wins=50, draws=30, losses=20)
    assert math.isclose(score_variance(o), 0.001525, rel_tol=1e-9)
    lo, hi = score_confidence_interval(o)
    assert math.isclose(lo, 0.65 - 0.0765374, abs_tol=1e-5)
    assert math.isclose(hi, 0.65 + 0.0765374, abs_tol=1e-5)


def test_score_variance_is_zero_variance_case_not_binomial():
    # A move that is either a hard win or hard loss with no draws (p=0.5,
    # split evenly) should have HIGHER per-game variance than one with the
    # same score achieved mostly via draws -- draws pull mass toward the
    # mean and reduce spread. The old binomial p(1-p)/n approximation
    # can't distinguish these two cases at all (same score -> same
    # variance under p(1-p)); the corrected formula must.
    decisive = MoveOutcome(label="decisive", wins=50, draws=0, losses=50)  # score 0.5
    draw_heavy = MoveOutcome(label="draws", wins=10, draws=80, losses=10)  # score 0.5
    assert decisive.score == draw_heavy.score == 0.5
    assert score_variance(decisive) > score_variance(draw_heavy)


def test_is_significantly_different_true_for_large_gap_large_n():
    a = MoveOutcome(label="a", wins=600, draws=200, losses=200)  # score 0.70
    b = MoveOutcome(label="b", wins=300, draws=200, losses=500)  # score 0.40
    assert is_significantly_different(a, b)


def test_is_significantly_different_false_for_tiny_samples():
    a = MoveOutcome(label="a", wins=3, draws=0, losses=1)  # score 0.75, n=4
    b = MoveOutcome(label="b", wins=1, draws=0, losses=3)  # score 0.25, n=4
    # Big gap in score but n is tiny -> should not be declared significant.
    assert not is_significantly_different(a, b)


def test_is_significantly_different_false_when_either_side_empty():
    a = MoveOutcome(label="a", wins=100, draws=0, losses=0)
    b = MoveOutcome(label="b", wins=0, draws=0, losses=0)
    assert not is_significantly_different(a, b)


def test_bootstrap_score_difference_none_when_either_side_empty():
    a = MoveOutcome(label="a", wins=10, draws=0, losses=0)
    b = MoveOutcome(label="b", wins=0, draws=0, losses=0)
    assert bootstrap_score_difference(a, b) is None


def test_bootstrap_score_difference_observed_diff_matches_point_estimate():
    a = MoveOutcome(label="a", wins=600, draws=200, losses=200)  # 0.70
    b = MoveOutcome(label="b", wins=300, draws=200, losses=500)  # 0.40
    result = bootstrap_score_difference(a, b, n_boot=5000, seed=42)
    assert math.isclose(result.observed_diff, 0.30, abs_tol=1e-9)
    # CI should be tight and clearly exclude 0 given the large n and gap.
    assert result.ci_lo > 0.15
    assert result.p_value < 0.01


def test_bootstrap_score_difference_no_real_difference_large_n_is_not_significant():
    # Same underlying rate, large n, different random samples -- the null
    # (no true difference) should not be rejected: CI should span 0 and
    # p_value should be large.
    a = MoveOutcome(label="a", wins=5000, draws=1000, losses=4000)  # score 0.55
    b = MoveOutcome(label="b", wins=5010, draws=990, losses=4000)  # score ~0.5505
    result = bootstrap_score_difference(a, b, n_boot=5000, seed=1)
    assert result.ci_lo < 0 < result.ci_hi
    assert result.p_value > 0.05


def test_compare_moves_bundles_z_test_and_bootstrap():
    a = MoveOutcome(label="a", wins=600, draws=200, losses=200)
    b = MoveOutcome(label="b", wins=300, draws=200, losses=500)
    result = compare_moves(a, b, n_boot=2000, seed=0)
    assert result.z_test_significant is True
    assert result.bootstrap is not None
    assert result.bootstrap.p_value < 0.05


def test_benjamini_hochberg_matches_hand_worked_reference_case():
    # Classic BH "staircase" example: 5 p-values, alpha=0.05.
    # thresholds (i/m * alpha) = 0.01, 0.02, 0.03, 0.04, 0.05
    # sorted p =                  0.01, 0.02, 0.03, 0.04, 0.50
    # p_i <= threshold_i for i=1..4, fails at i=5 -> reject ranks 1-4.
    # Adjusted p (q-value) = running-min from the top of (p_i * m / i):
    #   [0.05, 0.05, 0.05, 0.05, 0.50]
    p_values = [0.01, 0.02, 0.03, 0.04, 0.50]
    reject, adjusted = benjamini_hochberg(p_values, alpha=0.05)
    assert reject == [True, True, True, True, False]
    for got, want in zip(adjusted, [0.05, 0.05, 0.05, 0.05, 0.50]):
        assert math.isclose(got, want, abs_tol=1e-9)


def test_benjamini_hochberg_is_more_conservative_than_raw_alpha():
    # 3 genuinely small p-values buried among 7 large/noise p-values.
    # Naively thresholding raw p < 0.05 would flag all 3 small ones; BH,
    # correcting for 10 simultaneous tests, should flag fewer (here: none,
    # since 0.04 * 10 / 1 = 0.4 > 0.05 at the best rank).
    p_values = [0.04, 0.045, 0.049, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    raw_significant = sum(1 for p in p_values if p < 0.05)
    reject, _ = benjamini_hochberg(p_values, alpha=0.05)
    assert raw_significant == 3
    assert sum(reject) < raw_significant


def test_benjamini_hochberg_empty_input():
    assert benjamini_hochberg([]) == ([], [])


def test_benjamini_hochberg_all_significant_when_all_tiny():
    p_values = [1e-9, 1e-8, 1e-7, 1e-6]
    reject, adjusted = benjamini_hochberg(p_values, alpha=0.05)
    assert all(reject)
    assert all(a <= 0.05 for a in adjusted)


def test_confident_ranking_drops_small_samples_and_sorts_by_score():
    outcomes = [
        MoveOutcome(label="tiny_but_perfect", wins=5, draws=0, losses=0),  # n=5, dropped
        MoveOutcome(label="solid_second", wins=5500, draws=2000, losses=2500),  # score .65, n=10000
        MoveOutcome(label="solid_first", wins=7000, draws=1000, losses=2000),  # score .75, n=10000
    ]
    ranked = confident_ranking(outcomes, min_sample_size=30)
    assert [o.label for o in ranked] == ["solid_first", "solid_second"]


def test_confident_ranking_respects_custom_threshold():
    outcomes = [MoveOutcome(label="a", wins=5, draws=0, losses=0)]
    assert confident_ranking(outcomes, min_sample_size=30) == []
    assert confident_ranking(outcomes, min_sample_size=5) != []


def test_wilson_interval_bounds_are_within_unit_range():
    for p, n in [(0.0, 10), (1.0, 10), (0.5, 1)]:
        lo, hi = wilson_interval(p, n)
        assert 0.0 <= lo <= hi <= 1.0
        assert not math.isnan(lo) and not math.isnan(hi)
