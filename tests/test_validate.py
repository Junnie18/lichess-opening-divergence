from opening_divergence.validate import build_node_index, outcome_from_band_dict


def move(san, wins, draws, losses):
    return {"san": san, "wins": wins, "draws": draws, "losses": losses}


def test_build_node_index_keys_by_path_uci_tuple():
    nodes = [
        {"path_uci": ["e2e4"], "label": "a"},
        {"path_uci": ["d2d4", "d7d5"], "label": "b"},
    ]
    index = build_node_index(nodes)
    assert index[("e2e4",)]["label"] == "a"
    assert index[("d2d4", "d7d5")]["label"] == "b"
    assert len(index) == 2


def test_outcome_from_band_dict_found():
    node = {"lichess": {"blitz": {"validation": {"1600": {"e2e4": move("e4", 100, 50, 50)}}}}}
    out = outcome_from_band_dict(node, "blitz", "validation", "1600", "e2e4")
    assert out is not None
    assert out.wins == 100 and out.draws == 50 and out.losses == 50


def test_outcome_from_band_dict_missing_move_returns_none():
    node = {"lichess": {"blitz": {"validation": {"1600": {}}}}}
    assert outcome_from_band_dict(node, "blitz", "validation", "1600", "e2e4") is None


def test_outcome_from_band_dict_missing_band_returns_none():
    node = {"lichess": {"blitz": {"validation": {}}}}
    assert outcome_from_band_dict(node, "blitz", "validation", "1600", "e2e4") is None


def test_outcome_from_band_dict_missing_window_or_speed_returns_none():
    node = {"lichess": {"blitz": {"discovery": {"1600": {"e2e4": move("e4", 1, 1, 1)}}}}}
    assert outcome_from_band_dict(node, "blitz", "validation", "1600", "e2e4") is None
    assert outcome_from_band_dict(node, "rapid", "discovery", "1600", "e2e4") is None
