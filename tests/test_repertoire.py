from opening_divergence.repertoire import nearest_band, own_score, rank_candidates
from opening_divergence.stats import MoveOutcome
from opening_divergence.tree import CandidateMove


def make_candidate(uci, san, wins, draws, losses):
    outcome = MoveOutcome(label=san, wins=wins, draws=draws, losses=losses)
    return CandidateMove(uci=uci, san=san, outcome=outcome)


def test_nearest_band_exact_boundary():
    assert nearest_band(1400) == 1400


def test_nearest_band_rounds_down():
    assert nearest_band(1550) == 1400
    assert nearest_band(999) == 0
    assert nearest_band(3000) == 2500


def test_own_score_white_vs_black_perspective():
    c = make_candidate("e7e5", "e5", wins=60, draws=20, losses=20)  # White score 0.70
    assert own_score(c, mover_is_white=True) == 0.70
    assert abs(own_score(c, mover_is_white=False) - 0.30) < 1e-9


def test_rank_candidates_drops_zero_game_moves_and_sorts_for_mover():
    candidates = [
        make_candidate("a", "a", wins=0, draws=0, losses=0),  # no games, dropped
        make_candidate("b", "b", wins=20, draws=10, losses=70),  # white score 0.30
        make_candidate("c", "c", wins=70, draws=10, losses=20),  # white score 0.75
    ]
    ranked_for_white = rank_candidates(candidates, mover_is_white=True)
    assert [c.uci for c in ranked_for_white] == ["c", "b"]

    ranked_for_black = rank_candidates(candidates, mover_is_white=False)
    assert [c.uci for c in ranked_for_black] == ["b", "c"]
