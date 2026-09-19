#!/usr/bin/env python3
"""Generate the figures used in docs/article.md from the real pipeline output
(data/processed/*.json). Reads only -- never touches the analysis itself.

Usage:
    python scripts/generate_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "docs" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

# Palette (light mode, validated categorical/status steps -- see dataviz skill).
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#c98500"  # dark-step warning, legible as a small marker on light surface
STATUS_CRITICAL = "#d03b3b"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "text.color": INK_PRIMARY,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "axes.grid": False,
        "font.size": 11,
    }
)


def load(name):
    with open(PROCESSED / name) as f:
        return json.load(f)


def style_axes(ax, x_grid=False, y_grid=True):
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(BASELINE)
        ax.spines[spine].set_linewidth(1)
    if y_grid:
        ax.yaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    if x_grid:
        ax.xaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


# --- Figure 1: distribution of divergence magnitudes -----------------------


def fig_magnitude_distribution():
    d = load("discovery_findings.json")
    mags = [abs(f["observed_diff"]) for f in d["findings"] if f["fdr_significant"]]
    mags = np.array(mags)
    median = np.median(mags)

    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.arange(0, mags.max() + 0.02, 0.02)
    ax.hist(mags, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=0.5, zorder=2)
    ax.axvline(median, color=INK_SECONDARY, linewidth=1.5, linestyle=(0, (4, 2)), zorder=3)
    ax.annotate(
        f"median = {median:.3f}",
        xy=(median, ax.get_ylim()[1]),
        xytext=(median + 0.02, ax.get_ylim()[1]),
        va="top",
        fontsize=10,
        color=INK_SECONDARY,
    )
    style_axes(ax)
    ax.set_xlabel("Magnitude of score divergence between the two moves compared (abs. score gap)")
    ax.set_ylabel("Number of findings")
    ax.set_title(
        f"How big are the {len(mags):,} FDR-significant divergences?",
        fontsize=13,
        fontweight="bold",
        loc="left",
        pad=14,
    )
    fig.text(
        0.01,
        -0.02,
        "Score = (wins + 0.5×draws)/total, so a gap of 0.10 means roughly a 10-point swing in expected\n"
        "result out of 100. Discovery window, blitz, all three finding types combined.",
        fontsize=8.5,
        color=INK_MUTED,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "01_magnitude_distribution.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"fig 1: n={len(mags)}, median={median:.4f}, max={mags.max():.4f}")


# --- Figure 2: discovery vs validation scatter ------------------------------


def fig_discovery_vs_validation():
    d = load("validation_results.json")
    good_x, good_y = [], []
    warn_x, warn_y = [], []
    crit_x, crit_y = [], []
    for r in d["results"]:
        if r["untestable_reason"] is not None or r.get("validation_observed_diff") is None:
            continue
        x, y = r["discovery_observed_diff"], r["validation_observed_diff"]
        if r["replicated"]:
            good_x.append(x)
            good_y.append(y)
        elif r["direction_matches"]:
            warn_x.append(x)
            warn_y.append(y)
        else:
            crit_x.append(x)
            crit_y.append(y)

    fig, ax = plt.subplots(figsize=(7, 7))
    lo = min(good_x + warn_x + crit_x + good_y + warn_y + crit_y) - 0.03
    hi = max(good_x + warn_x + crit_x + good_y + warn_y + crit_y) + 0.03
    ax.plot([lo, hi], [lo, hi], color=INK_MUTED, linewidth=1, zorder=1)
    ax.annotate(
        "y = x (perfect replication)",
        xy=(hi * 0.62, hi * 0.62),
        rotation=45,
        fontsize=8.5,
        color=INK_MUTED,
        ha="left",
        va="bottom",
    )
    ax.scatter(
        crit_x, crit_y, s=16, c=STATUS_CRITICAL, alpha=0.75, linewidths=0, zorder=3, label="Flipped direction"
    )
    ax.scatter(
        warn_x,
        warn_y,
        s=16,
        c=STATUS_WARNING,
        alpha=0.65,
        linewidths=0,
        zorder=2,
        label="Direction held, not significant",
    )
    ax.scatter(good_x, good_y, s=14, c=STATUS_GOOD, alpha=0.55, linewidths=0, zorder=2, label="Replicated")
    style_axes(ax, y_grid=True, x_grid=True)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Score gap observed in discovery window (2016–22)")
    ax.set_ylabel("Score gap observed in validation window (2023–26)")
    ax.set_title(
        "Discovery-window gaps vs. what validation actually saw",
        fontsize=13,
        fontweight="bold",
        loc="left",
        pad=14,
    )
    ax.legend(frameon=False, loc="upper left", fontsize=9, markerscale=1.8)
    fig.text(
        0.01,
        -0.02,
        f"n={len(good_x)+len(warn_x)+len(crit_x):,} testable headline findings. Points near the\n"
        "diagonal replicated almost exactly; points that cross zero on the y-axis flipped sign.",
        fontsize=8.5,
        color=INK_MUTED,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "02_discovery_vs_validation.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"fig 2: good={len(good_x)}, warn={len(warn_x)}, crit={len(crit_x)}")


# --- Figure 3: concentration risk by rating band ----------------------------


def fig_concentration_by_band():
    d = load("concentration_results.json")
    bands = ["1000", "1200", "1400", "1600", "1800", "2000", "2200", "2500"]
    counts = {b: [0, 0] for b in bands}  # [n, risk]
    for r in d["results"]:
        b = r["band"]
        if b not in counts:
            continue
        counts[b][0] += 1
        if r["concentration_risk"]:
            counts[b][1] += 1
    rates = [100 * counts[b][1] / counts[b][0] for b in bands]
    ns = [counts[b][0] for b in bands]
    overall = 100 * d["n_concentration_risk"] / d["n_headline_recommendations_checked"]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(bands))
    ax.bar(x, rates, width=0.55, color=BLUE, zorder=2)
    ax.axhline(overall, color=INK_SECONDARY, linewidth=1.2, linestyle=(0, (4, 2)), zorder=1)
    ax.annotate(
        f"overall {overall:.1f}%",
        xy=(len(bands) - 1, overall),
        xytext=(len(bands) - 1, overall + 2.5),
        fontsize=9,
        color=INK_SECONDARY,
        ha="right",
    )
    for xi, r in zip(x, rates):
        ax.annotate(
            f"{r:.1f}%",
            xy=(xi, r),
            xytext=(xi, r + 1),
            ha="center",
            fontsize=9,
            color=INK_PRIMARY,
        )
    style_axes(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{b}\n(n={n})" for b, n in zip(bands, ns)], fontsize=9)
    ax.set_ylim(0, max(rates) + 8)
    ax.set_xlabel("Lichess rating band")
    ax.set_ylabel("Concentration-risk rate (HHI > 0.5)")
    ax.set_title(
        "Counter-repertoire risk rises sharply with rating",
        fontsize=13,
        fontweight="bold",
        loc="left",
        pad=14,
    )
    fig.text(
        0.01,
        -0.05,
        "Share of headline popularity-gap recommendations whose score is driven mostly by one\n"
        "specific opponent reply, rather than a broad spread, by the band the recommendation is for.",
        fontsize=8.5,
        color=INK_MUTED,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "03_concentration_by_band.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"fig 3: rates={[round(r,1) for r in rates]}")


# --- Figure 4: replication rate across robustness checks --------------------


def fig_replication_comparison():
    val = load("validation_results.json")
    cross = load("cross_speed_results.json")

    rows = [
        ("Out-of-sample\n(same speed, later years)", val["replication_rate"] * 100),
        ("Same window, rapid\n(different speed)", cross["rapid"]["replication_rate"] * 100),
        ("Same window, classical\n(different speed)", cross["classical"]["replication_rate"] * 100),
    ]
    rows.sort(key=lambda r: r[1], reverse=True)
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    y = np.arange(len(labels))
    ax.barh(y, values, height=0.5, color=BLUE, zorder=2)
    for yi, v in zip(y, values):
        ax.annotate(
            f"{v:.1f}%", xy=(v, yi), xytext=(v + 1.5, yi), va="center", fontsize=10, color=INK_PRIMARY
        )
    style_axes(ax, y_grid=False, x_grid=True)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of headline findings that hold up (%)")
    ax.set_title(
        "Findings are more time-stable than speed-stable",
        fontsize=13,
        fontweight="bold",
        loc="left",
        pad=14,
    )
    fig.text(
        0.01,
        -0.05,
        "Same 2,410 blitz headline findings, re-tested three ways: against later blitz data (out-of-\n"
        "sample), and against same-era rapid/classical data (cross-speed). Time controls diverge more\n"
        "than time periods do.",
        fontsize=8.5,
        color=INK_MUTED,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "04_replication_comparison.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"fig 4: {list(zip(labels, values))}")


if __name__ == "__main__":
    fig_magnitude_distribution()
    fig_discovery_vs_validation()
    fig_concentration_by_band()
    fig_replication_comparison()
    print("done ->", FIGURES)
