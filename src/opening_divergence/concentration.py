"""Concentration/outlier logic for scripts/concentration_check.py.

For a headline "popular move X underperforms less-popular move Y"
recommendation, the natural adversarial question is: is Y actually good
against a broad range of opponent replies, or does its score come almost
entirely from one narrow sub-line (e.g. a trap that only works if the
opponent replies one specific, possibly-bad way)? The latter is a much
weaker recommendation -- an opponent who doesn't fall into the trap
erases the advantage entirely.

We measure this with the Herfindahl-Hirschman Index (HHI) over the
distribution of the OPPONENT's replies to the recommended move: HHI is the
sum of squared market shares, ranging from 1/n (n options, perfectly even
split -- broad-based) to 1 (one option, all games -- maximally
concentrated). It's the standard concentration measure from industrial
economics, repurposed here for "concentration of an opening line's
supporting evidence" instead of market share.
"""

from __future__ import annotations

# HHI above this is flagged as a concentration risk: roughly, HHI=0.5 with
# only two options means a 71/29 split (0.71^2+0.29^2=0.5+0.084=0.588,
# close); with many options it takes an even more lopsided single-move
# dominance to reach 0.5, so this threshold is conservative (favors
# flagging real concentration over false alarms on plausibly-even splits).
CONCENTRATION_RISK_THRESHOLD = 0.5


def herfindahl_index(counts: list[int]) -> float | None:
    """HHI over a distribution of counts (e.g. opponent replies' game
    totals). Returns None if there are no games at all."""
    total = sum(counts)
    if total == 0:
        return None
    return sum((c / total) ** 2 for c in counts)


def is_concentration_risk(hhi: float | None, threshold: float = CONCENTRATION_RISK_THRESHOLD) -> bool:
    if hhi is None:
        return False
    return hhi > threshold


def dominant_share(counts: list[int]) -> float | None:
    """Share of games accounted for by the single most common reply --
    a more directly interpretable companion number to HHI (e.g. "83% of
    games saw one specific reply")."""
    total = sum(counts)
    if total == 0:
        return None
    return max(counts) / total
