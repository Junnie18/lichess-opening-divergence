from opening_divergence.divergence import (
    analyze_best_move_shift,
    analyze_master_theory,
    analyze_popularity_gap,
    confident_best_uci,
    most_popular_uci,
    render_markdown,
)

RATING_BANDS = [1000, 2500]


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


def test_confident_best_uci_ignores_small_samples():
    band_moves = {
        "tiny": move("Tiny", 5, 0, 0),  # n=5, perfect score, but too small
        "solid": move("Solid", 550, 100, 350),  # n=1000, score .675
    }
    assert confident_best_uci(band_moves, min_n=30) == "solid"


def test_most_popular_uci_picks_highest_n():
    band_moves = {"a": move("A", 10, 0, 0), "b": move("B", 40, 40, 40)}
    assert most_popular_uci(band_moves) == "b"


def test_analyze_best_move_shift_detects_divergence():
    node = {
        "path_san": "1. e4 e5",
        "lichess_by_band": {
            "1000": {
                "popular_bad": move("PopularBad", 300, 100, 600),  # score .35
                "niche_good": move("NicheGood", 60, 20, 20),  # score .70, n=100
            },
            "2500": {
                "popular_bad": move("PopularBad", 700, 100, 200),  # score .75
                "niche_good": move("NicheGood", 200, 100, 200),  # score .60, n=500
            },
        },
    }
    result = analyze_best_move_shift(node, RATING_BANDS, min_n=30)
    assert result is not None
    assert result["low_best"]["uci"] == "niche_good"
    assert result["high_best"]["uci"] == "popular_bad"
    assert result["low_favorite_at_high_band"]["san"] == "NicheGood"
    assert result["high_favorite_at_low_band"]["san"] == "PopularBad"


def test_analyze_best_move_shift_none_when_same_move_wins_everywhere():
    node = {
        "path_san": "1. d4 d5",
        "lichess_by_band": {
            "1000": {"a": move("A", 700, 100, 200)},
            "2500": {"a": move("A", 700, 100, 200)},
        },
    }
    assert analyze_best_move_shift(node, RATING_BANDS, min_n=30) is None


def test_analyze_popularity_gap_flags_significant_underperformer():
    node = {
        "path_san": "1. e4 c5",
        "lichess_by_band": {
            "1000": {
                "popular": move("Popular", 300, 100, 600),  # score .35, n=1000
                "better": move("Better", 700, 100, 200),  # score .75, n=1000
            }
        },
    }
    gaps = analyze_popularity_gap(node, [1000], min_n=30)
    assert len(gaps) == 1
    assert gaps[0]["popular"]["uci"] == "popular"
    assert gaps[0]["better"]["uci"] == "better"
    assert gaps[0]["score_gap"] > 0


def test_analyze_popularity_gap_empty_when_popular_move_is_also_best():
    node = {
        "path_san": "1. e4 c5",
        "lichess_by_band": {"1000": {"a": move("A", 700, 100, 200)}},
    }
    assert analyze_popularity_gap(node, [1000], min_n=30) == []


def test_analyze_master_theory_returns_none_without_masters_data():
    node = {"path_san": "x", "lichess_by_band": {}, "masters": None}
    assert analyze_master_theory(node, RATING_BANDS, min_n=30) is None


def test_analyze_master_theory_compares_low_and_high_band():
    node = {
        "path_san": "1. e4 e5 2. Nf3 Nc6 3. Bb5",
        "masters": {"main": move("Main", 400, 400, 200)},
        "lichess_by_band": {
            "1000": {"main": move("Main", 200, 100, 700)},  # score .25 at low band
            "2500": {"main": move("Main", 600, 300, 100)},  # score .75 at high band
        },
    }
    result = analyze_master_theory(node, RATING_BANDS, min_n=30)
    assert result is not None
    assert result["at_low_band"]["score"] == 0.25
    assert result["at_high_band"]["score"] == 0.75


def test_render_markdown_handles_empty_findings_without_crashing():
    findings = {
        "tree_generated_at": "2026-01-01T00:00:00Z",
        "speed": "blitz",
        "rating_bands": RATING_BANDS,
        "min_sample_size": 30,
        "best_move_shifts": [],
        "popularity_gaps": [],
        "master_theory": [],
    }
    md = render_markdown(findings)
    assert "Generated divergence findings" in md
    assert "None found" in md
