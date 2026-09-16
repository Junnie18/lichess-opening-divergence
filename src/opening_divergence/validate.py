"""Shared lookup helpers for re-testing a discovery-window Finding against
a different window or speed's data -- used by both
scripts/validate_findings.py (different time window) and
scripts/cross_speed_check.py (different speed, same window). Split out so
both scripts share one tested implementation of "find this exact
comparison's data elsewhere in the tree" rather than duplicating it.
"""

from __future__ import annotations

from .stats import MoveOutcome


def build_node_index(nodes: list[dict]) -> dict[tuple, dict]:
    return {tuple(n["path_uci"]): n for n in nodes}


def outcome_from_band_dict(node: dict, speed: str, window: str, band: str, uci: str) -> MoveOutcome | None:
    d = node.get("lichess", {}).get(speed, {}).get(window, {}).get(band, {}).get(uci)
    if d is None:
        return None
    return MoveOutcome(label=d["san"], wins=d["wins"], draws=d["draws"], losses=d["losses"])
