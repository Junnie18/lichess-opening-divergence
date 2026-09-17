"""Pure analysis logic behind scripts/analyze_divergence.py and
scripts/validate_findings.py, split out so it can be unit-tested against
synthetic opening-tree fixtures without running the real data collection
pipeline.

Design note on p-values and FDR: the functions here compute a *raw*
bootstrap p-value per comparison but deliberately do NOT decide
significance themselves. With hundreds of positions x bands x speeds,
significance decisions must be made once, across the *entire* family of
comparisons produced in a single analysis run, via Benjamini-Hochberg
(``opening_divergence.stats.benjamini_hochberg``) -- that's the caller's
job (see scripts/analyze_divergence.py), not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats import BootstrapComparison, MoveOutcome, bootstrap_score_difference


def _outcome_from_dict(d: dict) -> MoveOutcome:
    return MoveOutcome(label=d["san"], wins=d["wins"], draws=d["draws"], losses=d["losses"])


def confident_best_uci(band_moves: dict, min_n: int) -> str | None:
    best_uci, best_score = None, -1.0
    for uci, d in band_moves.items():
        if d["total"] < min_n:
            continue
        if d["score"] > best_score:
            best_uci, best_score = uci, d["score"]
    return best_uci


def most_popular_uci(band_moves: dict) -> str | None:
    if not band_moves:
        return None
    return max(band_moves.items(), key=lambda kv: kv[1]["total"])[0]


@dataclass
class Finding:
    """One comparison in the analysis family, carrying everything needed to
    report it plus its raw p-value. FDR-adjustment fields are filled in
    later by the caller once the whole family's p-values are known."""

    kind: str  # "best_move_shift" | "popularity_gap" | "master_theory"
    path_san: str
    path_uci: list[str]
    speed: str
    window: str
    band_a: str  # band (or "masters") the `a` outcome is drawn from
    band_b: str
    a_uci: str
    a: dict
    b_uci: str
    b: dict
    bootstrap: BootstrapComparison
    detail: dict = field(default_factory=dict)  # kind-specific extra context

    @property
    def raw_p_value(self) -> float:
        return self.bootstrap.p_value

    def key(self) -> tuple:
        """Identity used to look up the SAME comparison in another window
        (e.g. re-testing a discovery finding against validation data)."""
        return (self.kind, tuple(self.path_uci), self.speed, self.band_a, self.band_b, self.a_uci, self.b_uci)


def best_move_shift_findings(
    node: dict,
    rating_bands: list[int],
    min_n: int,
    speed: str,
    window: str,
    n_boot: int = 10000,
    seed: int = 0,
) -> list[Finding]:
    """For a position, find whether the confidently-best move differs
    between the lowest and highest rating band with a confident best move.
    If it does, return TWO findings -- the low-best-vs-high-best comparison
    evaluated AT the low band, and the same pair evaluated AT the high band
    -- so both directions of the claimed shift get their own p-value
    instead of asserting a "shift" off unlabeled point estimates.
    """
    by_band = node["lichess"][speed][window]
    band_keys = [str(b) for b in rating_bands if str(b) in by_band]
    confident = {bk: confident_best_uci(by_band[bk], min_n) for bk in band_keys}
    confident = {bk: uci for bk, uci in confident.items() if uci is not None}
    ordered = [bk for bk in band_keys if bk in confident]
    if len(ordered) < 2:
        return []

    low_band, high_band = ordered[0], ordered[-1]
    low_uci, high_uci = confident[low_band], confident[high_band]
    if low_uci == high_uci:
        return []

    findings = []
    for eval_band in (low_band, high_band):
        band_moves = by_band[eval_band]
        if low_uci not in band_moves or high_uci not in band_moves:
            continue
        a_d, b_d = band_moves[low_uci], band_moves[high_uci]
        if a_d["total"] < min_n or b_d["total"] < min_n:
            # Confidence at low_band/high_band doesn't imply confidence at the
            # OTHER band being evaluated here -- a move can be well-sampled where
            # it's popular and barely played (n=1) where it isn't. Un-gated, the
            # bootstrap's resampled-from-the-MLE-outcome CI degenerates toward
            # zero width as n->1 (it has nothing to resample variation from),
            # producing spuriously "significant" findings. See popularity_gap/
            # master_theory below, which already gate both sides this way.
            continue
        boot = bootstrap_score_difference(
            _outcome_from_dict(a_d), _outcome_from_dict(b_d), n_boot=n_boot, seed=seed
        )
        if boot is None:
            continue
        findings.append(
            Finding(
                kind="best_move_shift",
                path_san=node["path_san"],
                path_uci=node["path_uci"],
                speed=speed,
                window=window,
                band_a=eval_band,
                band_b=eval_band,
                a_uci=low_uci,
                a={"uci": low_uci, **a_d},
                b_uci=high_uci,
                b={"uci": high_uci, **b_d},
                bootstrap=boot,
                detail={"low_band": low_band, "high_band": high_band, "evaluated_at": eval_band},
            )
        )
    return findings


def popularity_gap_findings(
    node: dict,
    rating_bands: list[int],
    min_n: int,
    speed: str,
    window: str,
    n_boot: int = 10000,
    seed: int = 0,
) -> list[Finding]:
    """Positions where the most popular move is not the best-scoring
    (confident) one, per rating band."""
    by_band = node["lichess"][speed][window]
    findings = []
    for band in rating_bands:
        bk = str(band)
        band_moves = by_band.get(bk)
        if not band_moves:
            continue
        pop_uci = most_popular_uci(band_moves)
        best_uci = confident_best_uci(band_moves, min_n)
        if not pop_uci or not best_uci or pop_uci == best_uci:
            continue
        pop_d, best_d = band_moves[pop_uci], band_moves[best_uci]
        if pop_d["total"] < min_n:
            continue
        boot = bootstrap_score_difference(
            _outcome_from_dict(best_d), _outcome_from_dict(pop_d), n_boot=n_boot, seed=seed
        )
        if boot is None:
            continue
        findings.append(
            Finding(
                kind="popularity_gap",
                path_san=node["path_san"],
                path_uci=node["path_uci"],
                speed=speed,
                window=window,
                band_a=bk,
                band_b=bk,
                a_uci=best_uci,
                a={"uci": best_uci, **best_d},
                b_uci=pop_uci,
                b={"uci": pop_uci, **pop_d},
                bootstrap=boot,
                detail={"band": bk},
            )
        )
    return findings


def master_theory_findings(
    node: dict,
    rating_bands: list[int],
    min_n: int,
    speed: str,
    window: str,
    n_boot: int = 10000,
    seed: int = 0,
) -> list[Finding]:
    """Does the masters' most-played move's score at the lowest Lichess
    band differ significantly from its score at the highest band?"""
    masters = node.get("masters")
    by_band = node["lichess"][speed][window]
    if not masters:
        return []
    master_top_uci = most_popular_uci(masters)
    if not master_top_uci:
        return []

    lowest_band, highest_band = str(min(rating_bands)), str(max(rating_bands))
    low_d = by_band.get(lowest_band, {}).get(master_top_uci)
    high_d = by_band.get(highest_band, {}).get(master_top_uci)
    if not low_d or not high_d or low_d["total"] < min_n or high_d["total"] < min_n:
        return []

    boot = bootstrap_score_difference(
        _outcome_from_dict(high_d), _outcome_from_dict(low_d), n_boot=n_boot, seed=seed
    )
    if boot is None:
        return []
    return [
        Finding(
            kind="master_theory",
            path_san=node["path_san"],
            path_uci=node["path_uci"],
            speed=speed,
            window=window,
            band_a=highest_band,
            band_b=lowest_band,
            a_uci=master_top_uci,
            a={"uci": master_top_uci, **high_d},
            b_uci=master_top_uci,
            b={"uci": master_top_uci, **low_d},
            bootstrap=boot,
            detail={"masters_top": {"uci": master_top_uci, **masters[master_top_uci]}},
        )
    ]


def build_finding_family(
    nodes: list[dict], rating_bands: list[int], min_n: int, speed: str, window: str, n_boot: int = 10000
) -> list[Finding]:
    """All three finding types, across every node, for one speed+window.
    This IS "the full family of is-move-A-better-than-move-B tests" that
    Benjamini-Hochberg correction must be applied across (see caller)."""
    findings: list[Finding] = []
    for i, node in enumerate(nodes):
        findings.extend(
            best_move_shift_findings(node, rating_bands, min_n, speed, window, n_boot=n_boot, seed=i)
        )
        findings.extend(
            popularity_gap_findings(node, rating_bands, min_n, speed, window, n_boot=n_boot, seed=i)
        )
        findings.extend(
            master_theory_findings(node, rating_bands, min_n, speed, window, n_boot=n_boot, seed=i)
        )
    return findings
