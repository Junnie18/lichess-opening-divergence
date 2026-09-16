import math

from opening_divergence.stats import (
    MoveOutcome,
    confident_ranking,
    is_significantly_different,
    score_confidence_interval,
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


def test_low_confidence_flag():
    small = MoveOutcome(label="rare", wins=2, draws=1, losses=1)
    big = MoveOutcome(label="popular", wins=500, draws=300, losses=200)
    assert small.low_confidence
    assert not big.low_confidence


def test_wilson_interval_contains_point_estimate_and_narrows_with_n():
    lo_small, hi_small = wilson_interval(0.5, 20)
    lo_big, hi_big = wilson_interval(0.5, 20000)
    assert lo_small <= 0.5 <= hi_small
    assert lo_big <= 0.5 <= hi_big
    assert (hi_big - lo_big) < (hi_small - lo_small)


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


def test_confident_ranking_drops_small_samples_and_sorts_by_score():
    outcomes = [
        MoveOutcome(label="tiny_but_perfect", wins=5, draws=0, losses=0),  # n=5, dropped
        MoveOutcome(label="solid_second", wins=550, draws=200, losses=250),  # score .65, n=1000
        MoveOutcome(label="solid_first", wins=700, draws=100, losses=200),  # score .75, n=1000
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
