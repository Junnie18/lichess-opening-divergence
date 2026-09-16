"""Pure analysis logic behind scripts/analyze_divergence.py, split out so
it can be unit-tested against synthetic opening-tree fixtures without
running the real data collection pipeline.

See scripts/analyze_divergence.py's module docstring for what each finding
type means.
"""

from __future__ import annotations

from .stats import MoveOutcome, is_significantly_different


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


def analyze_best_move_shift(node: dict, rating_bands: list[int], min_n: int) -> dict | None:
    by_band = node["lichess_by_band"]
    band_keys = [str(b) for b in rating_bands if str(b) in by_band]
    confident = {bk: confident_best_uci(by_band[bk], min_n) for bk in band_keys}
    confident = {bk: uci for bk, uci in confident.items() if uci is not None}
    ordered = [bk for bk in band_keys if bk in confident]
    if len(ordered) < 2:
        return None

    low_band, high_band = ordered[0], ordered[-1]
    low_uci, high_uci = confident[low_band], confident[high_band]
    if low_uci == high_uci:
        return None

    low_best = {"uci": low_uci, **by_band[low_band][low_uci]}
    high_best = {"uci": high_uci, **by_band[high_band][high_uci]}

    return {
        "path_san": node["path_san"],
        "low_band": low_band,
        "high_band": high_band,
        "low_best": low_best,
        "high_best": high_best,
        "low_favorite_at_high_band": by_band[high_band].get(low_uci),
        "high_favorite_at_low_band": by_band[low_band].get(high_uci),
    }


def analyze_popularity_gap(node: dict, rating_bands: list[int], min_n: int) -> list[dict]:
    by_band = node["lichess_by_band"]
    gaps = []
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
        if not is_significantly_different(_outcome_from_dict(pop_d), _outcome_from_dict(best_d)):
            continue
        gaps.append(
            {
                "path_san": node["path_san"],
                "band": bk,
                "popular": {"uci": pop_uci, **pop_d},
                "better": {"uci": best_uci, **best_d},
                "score_gap": best_d["score"] - pop_d["score"],
            }
        )
    return gaps


def analyze_master_theory(node: dict, rating_bands: list[int], min_n: int) -> dict | None:
    masters = node.get("masters")
    by_band = node["lichess_by_band"]
    if not masters:
        return None
    master_top_uci = most_popular_uci(masters)
    if not master_top_uci:
        return None

    lowest_band, highest_band = str(min(rating_bands)), str(max(rating_bands))
    low_d = by_band.get(lowest_band, {}).get(master_top_uci)
    high_d = by_band.get(highest_band, {}).get(master_top_uci)
    if not low_d and not high_d:
        return None

    return {
        "path_san": node["path_san"],
        "master_top": {"uci": master_top_uci, **masters[master_top_uci]},
        "low_band": lowest_band,
        "at_low_band": low_d,
        "high_band": highest_band,
        "at_high_band": high_d,
    }


def render_markdown(findings: dict) -> str:
    lines = ["# Generated divergence findings", ""]
    lines.append(
        f"Generated from `{findings['tree_generated_at']}` opening-tree data, "
        f"speed=**{findings['speed']}**, rating bands={findings['rating_bands']}, "
        f"min-sample-size={findings['min_sample_size']}."
    )
    lines.append("")

    lines.append("## 1. Positions where the best-scoring move changes with rating")
    lines.append("")
    if not findings["best_move_shifts"]:
        lines.append("_None found at the current sample-size threshold._")
    else:
        lines.append(
            "| Position | Low band best | Low band's move score at high band | "
            "High band best | High band's move score at low band |"
        )
        lines.append("|---|---|---|---|---|")
        for f in findings["best_move_shifts"]:
            lb, hb = f["low_best"], f["high_best"]
            low_at_high = f["low_favorite_at_high_band"]
            high_at_low = f["high_favorite_at_low_band"]
            low_at_high_s = (
                f"{low_at_high['score']:.3f} (n={low_at_high['total']})" if low_at_high else "no data"
            )
            high_at_low_s = (
                f"{high_at_low['score']:.3f} (n={high_at_low['total']})" if high_at_low else "no data"
            )
            lines.append(
                f"| {f['path_san']} | {lb['san']} @{f['low_band']}+: {lb['score']:.3f} (n={lb['total']}) "
                f"| {low_at_high_s} @{f['high_band']}+ "
                f"| {hb['san']} @{f['high_band']}+: {hb['score']:.3f} (n={hb['total']}) "
                f"| {high_at_low_s} @{f['low_band']}+ |"
            )
    lines.append("")

    lines.append("## 2. Popular moves that underperform a less-popular alternative")
    lines.append("")
    if not findings["popularity_gaps"]:
        lines.append("_None found at the current sample-size / significance threshold._")
    else:
        lines.append("| Position | Band | Popular move | Better move | Score gap |")
        lines.append("|---|---|---|---|---|")
        for g in findings["popularity_gaps"]:
            p, b = g["popular"], g["better"]
            lines.append(
                f"| {g['path_san']} | {g['band']}+ | {p['san']}: {p['score']:.3f} (n={p['total']}) "
                f"| {b['san']}: {b['score']:.3f} (n={b['total']}) | {g['score_gap']:+.3f} |"
            )
    lines.append("")

    lines.append("## 3. Master-database main move vs. its score in the Lichess pool")
    lines.append("")
    if not findings["master_theory"]:
        lines.append("_No comparable data._")
    else:
        lines.append(
            "| Position | Masters' main move | Score at lowest band | Score at highest band | Delta |"
        )
        lines.append("|---|---|---|---|---|")
        for m in findings["master_theory"]:
            top = m["master_top"]
            low, high = m["at_low_band"], m["at_high_band"]
            low_s = f"{low['score']:.3f} (n={low['total']})" if low else "no data"
            high_s = f"{high['score']:.3f} (n={high['total']})" if high else "no data"
            delta = f"{high['score'] - low['score']:+.3f}" if low and high else "n/a"
            lines.append(
                f"| {m['path_san']} | {top['san']} (masters n={top['total']}) | {low_s} @{m['low_band']}+ "
                f"| {high_s} @{m['high_band']}+ | {delta} |"
            )
    lines.append("")

    return "\n".join(lines)
