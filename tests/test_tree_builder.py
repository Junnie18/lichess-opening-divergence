from opening_divergence.stats import MoveOutcome
from opening_divergence.tree import CandidateMove
from opening_divergence.tree_builder import Seed, build_positions

# Synthetic opening "book": path (tuple of uci) -> list of (uci, san, total_games).
# Total games double as popularity; win/draw/loss split doesn't matter here.
BOOK = {
    (): [("e2e4", "e4", 1000), ("d2d4", "d4", 900), ("g1f3", "Nf3", 50), ("c2c4", "c4", 40)],
    ("e2e4",): [("c7c5", "c5", 500), ("e7e5", "e5", 480), ("c7c6", "c6", 5)],  # c6 below 2% share
    ("e2e4", "c7c5"): [("g1f3", "Nf3", 300), ("b1c3", "Nc3", 200)],
    ("e2e4", "e7e5"): [("g1f3", "Nf3", 900)],
    ("d2d4",): [("d7d5", "d5", 700), ("g8f6", "Nf6", 690)],
}


def fake_get_candidates(path_uci):
    key = tuple(path_uci)
    entries = BOOK.get(key, [])
    return [
        CandidateMove(uci=uci, san=san, outcome=MoveOutcome(label=san, wins=n, draws=0, losses=0))
        for uci, san, n in entries
    ]


def test_build_positions_includes_seed_and_respects_extra_depth():
    seeds = [Seed(system="e4", path_uci=["e2e4"], extra_depth=0)]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    assert [n.path_uci for n in nodes] == [["e2e4"]]


def test_build_positions_expands_bfs_and_prunes_by_branch_factor_and_share():
    seeds = [Seed(system="e4", path_uci=["e2e4"], extra_depth=2)]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    paths = {tuple(n.path_uci) for n in nodes}
    # Seed itself.
    assert ("e2e4",) in paths
    # c5 and e5 both clear 2% share and top-2 by popularity -> expanded.
    assert ("e2e4", "c7c5") in paths
    assert ("e2e4", "e7e5") in paths
    # c6 has only 5/985 ~ 0.5% share -> pruned, never expanded into.
    assert ("e2e4", "c7c6") not in paths
    # One more ply from c5 and e5.
    assert ("e2e4", "c7c5", "g1f3") in paths
    assert ("e2e4", "e7e5", "g1f3") in paths


def test_build_positions_dedupes_across_seeds_and_unions_systems():
    seeds = [
        Seed(system="e4-generic", path_uci=["e2e4"], extra_depth=1),
        Seed(system="sicilian", path_uci=["e2e4", "c7c5"], extra_depth=0),
    ]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    sicilian_node = next(n for n in nodes if n.path_uci == ["e2e4", "c7c5"])
    assert set(sicilian_node.systems) == {"e4-generic", "sicilian"}


def test_build_positions_root_seed_with_empty_path():
    seeds = [Seed(system="root", path_uci=[], extra_depth=1)]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    paths = {tuple(n.path_uci) for n in nodes}
    assert () in paths
    assert ("e2e4",) in paths
    assert ("d2d4",) in paths
    # Nf3/c4 are below the 2% share threshold at the root (50/1990, 40/1990) -> pruned.
    assert ("g1f3",) not in paths
    assert ("c2c4",) not in paths


def test_build_positions_deterministic_order_sorted_by_depth_then_path():
    seeds = [Seed(system="e4", path_uci=["e2e4"], extra_depth=2)]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    depths = [len(n.path_uci) for n in nodes]
    assert depths == sorted(depths)


def test_build_positions_stops_expanding_when_no_candidates_available():
    seeds = [Seed(system="dead-end", path_uci=["g1f3"], extra_depth=3)]
    nodes = build_positions(seeds, fake_get_candidates, branch_factor=2, min_popularity_share=0.02)
    # BOOK has no entry for ("g1f3",) -> no children, but the seed node itself is still returned.
    assert [n.path_uci for n in nodes] == [["g1f3"]]
