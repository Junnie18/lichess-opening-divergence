from opening_divergence.divergence import (
    best_move_shift_findings,
    build_finding_family,
    confident_best_uci,
    master_theory_findings,
    most_popular_uci,
    popularity_gap_findings,
)

RATING_BANDS = [1000, 2500]
SPEED = "blitz"
WINDOW = "discovery"


def move(san, wins, draws, losses):
    total = wins + draws + losses
    return {
        "san": san,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "total": total,
        "win_rate": wins / total if total else None,
        "score": (wins + 0.5 * draws) / total if total else None,
        "low_confidence": total < 30,
    }


def make_node(path_san, path_uci, by_band, masters=None):
    return {
        "path_san": path_san,
        "path_uci": path_uci,
        "lichess": {SPEED: {WINDOW: by_band}},
        "masters": masters,
    }


def test_confident_best_uci_ignores_small_samples():
    band_moves = {
        "tiny": move("Tiny", 5, 0, 0),  # n=5, perfect score, but too small
        "solid": move("Solid", 550, 100, 350),  # n=1000, score .675
    }
    assert confident_best_uci(band_moves, min_n=30) == "solid"


def test_most_popular_uci_picks_highest_n():
    band_moves = {"a": move("A", 10, 0, 0), "b": move("B", 40, 40, 40)}
    assert most_popular_uci(band_moves) == "b"


def test_best_move_shift_detects_divergence_with_bootstrap_p_values():
    node = make_node(
        "1. e4 e5",
        ["e2e4", "e7e5"],
        {
            "1000": {
                "popular_bad": move("PopularBad", 3000, 1000, 6000),  # score .35, n=10000
                "niche_good": move("NicheGood", 6000, 2000, 2000),  # score .70, n=10000
            },
            "2500": {
                "popular_bad": move("PopularBad", 7000, 1000, 2000),  # score .75, n=10000
                "niche_good": move("NicheGood", 4000, 2000, 4000),  # score .60, n=10000
            },
        },
    )
    findings = best_move_shift_findings(node, RATING_BANDS, min_n=30, speed=SPEED, window=WINDOW)
    assert len(findings) == 2  # evaluated at low band and at high band
    assert {f.detail["evaluated_at"] for f in findings} == {"1000", "2500"}
    assert all(f.a_uci == "niche_good" and f.b_uci == "popular_bad" for f in findings)
    # Large gap, large n at both bands -> both should be clearly significant.
    assert all(f.raw_p_value < 0.01 for f in findings)


def test_best_move_shift_requires_min_n_on_both_sides_at_eval_band():
    # Each move is confidently "best" at its OWN band (n=10000 there), but
    # niche_good has only 1 game at the 2500 band -- that shouldn't be enough
    # to trust a bootstrap comparison evaluated at 2500, even though it clears
    # min_n at 1000. Regression test for a bug where cross-band evaluation
    # didn't re-check min_n at the band actually being evaluated.
    node = make_node(
        "1. e4 e5",
        ["e2e4", "e7e5"],
        {
            "1000": {
                "popular_bad": move("PopularBad", 3000, 1000, 6000),  # score .35, n=10000
                "niche_good": move("NicheGood", 6000, 2000, 2000),  # score .70, n=10000
            },
            "2500": {
                "popular_bad": move("PopularBad", 7000, 1000, 2000),  # score .75, n=10000
                "niche_good": move("NicheGood", 1, 0, 0),  # score 1.0, n=1 -- too small to trust
            },
        },
    )
    findings = best_move_shift_findings(node, RATING_BANDS, min_n=30, speed=SPEED, window=WINDOW)
    assert len(findings) == 1
    assert findings[0].detail["evaluated_at"] == "1000"


def test_best_move_shift_empty_when_same_move_wins_everywhere():
    node = make_node(
        "1. d4 d5",
        ["d2d4", "d7d5"],
        {"1000": {"a": move("A", 700, 100, 200)}, "2500": {"a": move("A", 700, 100, 200)}},
    )
    assert best_move_shift_findings(node, RATING_BANDS, min_n=30, speed=SPEED, window=WINDOW) == []


def test_popularity_gap_flags_significant_underperformer():
    node = make_node(
        "1. e4 c5",
        ["e2e4", "c7c5"],
        {
            "1000": {
                "popular": move("Popular", 3000, 1000, 6000),  # score .35, n=10000
                "better": move("Better", 7000, 1000, 2000),  # score .75, n=10000
            }
        },
    )
    findings = popularity_gap_findings(node, [1000], min_n=30, speed=SPEED, window=WINDOW)
    assert len(findings) == 1
    f = findings[0]
    assert f.a_uci == "better"
    assert f.b_uci == "popular"
    assert f.bootstrap.observed_diff > 0
    assert f.raw_p_value < 0.01


def test_popularity_gap_empty_when_popular_move_is_also_best():
    node = make_node("1. e4 c5", ["e2e4", "c7c5"], {"1000": {"a": move("A", 700, 100, 200)}})
    assert popularity_gap_findings(node, [1000], min_n=30, speed=SPEED, window=WINDOW) == []


def test_master_theory_returns_empty_without_masters_data():
    node = make_node("x", [], {}, masters=None)
    assert master_theory_findings(node, RATING_BANDS, min_n=30, speed=SPEED, window=WINDOW) == []


def test_master_theory_compares_low_and_high_band():
    node = make_node(
        "1. e4 e5 2. Nf3 Nc6 3. Bb5",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],
        {
            "1000": {"main": move("Main", 2000, 1000, 7000)},  # score .25 at low band, n=10000
            "2500": {"main": move("Main", 6000, 3000, 1000)},  # score .75 at high band, n=10000
        },
        masters={"main": move("Main", 400, 400, 200)},
    )
    findings = master_theory_findings(node, RATING_BANDS, min_n=30, speed=SPEED, window=WINDOW)
    assert len(findings) == 1
    f = findings[0]
    assert f.a["score"] == 0.75  # high band
    assert f.b["score"] == 0.25  # low band
    assert f.raw_p_value < 0.01


def test_build_finding_family_aggregates_across_nodes():
    node1 = make_node(
        "1. e4 c5",
        ["e2e4", "c7c5"],
        {"1000": {"popular": move("Popular", 3000, 1000, 6000), "better": move("Better", 7000, 1000, 2000)}},
    )
    node2 = make_node("1. d4 d5", ["d2d4", "d7d5"], {"1000": {"a": move("A", 700, 100, 200)}})
    findings = build_finding_family([node1, node2], [1000], min_n=30, speed=SPEED, window=WINDOW)
    assert len(findings) == 1
    assert findings[0].kind == "popularity_gap"


def test_finding_key_is_stable_identity_across_windows():
    # key() deliberately excludes `window`: it's the identity used to look
    # up the SAME comparison (same kind/position/speed/bands/moves) in a
    # different window, e.g. re-testing a discovery finding against
    # validation-window data (see scripts/validate_findings.py).
    by_band = {
        "1000": {"popular": move("Popular", 3000, 1000, 6000), "better": move("Better", 7000, 1000, 2000)}
    }
    node = {
        "path_san": "1. e4 c5",
        "path_uci": ["e2e4", "c7c5"],
        "lichess": {SPEED: {"discovery": by_band, "validation": by_band}},
        "masters": None,
    }
    f_discovery = popularity_gap_findings(node, [1000], min_n=30, speed=SPEED, window="discovery")[0]
    f_validation = popularity_gap_findings(node, [1000], min_n=30, speed=SPEED, window="validation")[0]
    assert f_discovery.key() == f_validation.key()
    assert f_discovery.window != f_validation.window
