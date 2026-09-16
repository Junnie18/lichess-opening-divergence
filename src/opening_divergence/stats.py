"""Win-rate / confidence math shared by the analysis scripts and the CLI.

Terminology: "score" means expected score from White's point of view --
``(wins + 0.5 * draws) / total`` -- the standard chess convention for
evaluating a move, since it correctly treats a draw as half a point rather
than discarding it (raw win-rate alone hides moves that draw heavily but
rarely lose). "win rate" (``wins / total``) is also exposed since the task
and most players talk in those terms, but ranking uses ``score`` unless
noted otherwise -- this is a documented assumption, not a hidden default.

This module has three layers:

1. ``MoveOutcome`` / variance / confidence-interval machinery, derived from
   first principles for the three-outcome (win/draw/loss) random variable
   rather than treating "score" as if it were a literal binomial
   proportion (a draw is not "half a success" in the binomial sense, and
   using the binomial variance formula ``p(1-p)/n`` understates/overstates
   the true spread -- see ``_per_game_score_variance`` for the derivation).
2. Two-sample comparison: a bootstrap test (primary; resamples directly
   from the reported W/D/L counts) plus a closed-form z-test (kept as a
   fast analytic cross-check -- see ``compare_moves``).
3. Multiple-comparisons correction (Benjamini-Hochberg FDR) and a
   power-calculation-derived minimum sample size, both needed because this
   project runs many "is move A better than move B" tests at once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Z_95 = 1.959963985  # z_{alpha/2} for alpha = 0.05 (two-sided 95% CI / test)
Z_POWER_80 = 0.8416212336  # z_beta for 80% power (beta = 0.20)

# --- Sample-size threshold, derived from an actual power calculation -----
#
# We want 80% power to detect a TARGET_EFFECT_SIZE_PP (percentage-point)
# difference in *score* between two moves at alpha=0.05, two-sided, using
# an equal-n two-sample z-test. Standard formula for the required n per
# group:
#
#   n = 2 * (z_{alpha/2} + z_{power})^2 * sigma^2 / delta^2
#
# sigma^2 is the per-game variance of the score random variable X in
# {0, 0.5, 1}. We use the conservative (variance-maximizing) case
# sigma^2 = 0.25, i.e. all mass split between the two extremes (win/loss)
# at p=0.5 with no draws -- the classical "worst case" for a [0,1]-bounded
# variable. Real chess data always has substantial draw mass, which
# strictly *reduces* variance relative to this bound (see
# ``_per_game_score_variance``: putting probability mass at 0.5 instead of
# the extremes pulls outcomes toward the mean), so this choice is
# conservative: it yields a required-n that is an upper bound, not an
# underestimate, of what real data needs.
TARGET_EFFECT_SIZE_PP = 0.04  # 4 percentage points, middle of the 3-5pp range
CONSERVATIVE_PER_GAME_VARIANCE = 0.25


def required_sample_size_per_group(
    effect_size: float = TARGET_EFFECT_SIZE_PP,
    alpha: float = 0.05,
    power: float = 0.80,
    variance: float = CONSERVATIVE_PER_GAME_VARIANCE,
) -> int:
    """Minimum n per group (per candidate move) for `power` probability of
    detecting a true score difference of `effect_size` at level `alpha`,
    two-sided, equal group sizes. See module docstring for the formula and
    the conservative-variance justification.
    """
    z_alpha2 = _z_two_sided(alpha)
    z_beta = _z_one_sided(power)
    n = 2 * (z_alpha2 + z_beta) ** 2 * variance / effect_size**2
    return math.ceil(n)


def _z_two_sided(alpha: float) -> float:
    if abs(alpha - 0.05) < 1e-9:
        return Z_95
    return _norm_ppf(1 - alpha / 2)


def _z_one_sided(power: float) -> float:
    if abs(power - 0.80) < 1e-9:
        return Z_POWER_80
    return _norm_ppf(power)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation,
    accurate to ~1.15e-9). Avoids a scipy dependency for the one or two
    non-default alpha/power values a caller might pass."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


MIN_SAMPLE_SIZE = required_sample_size_per_group()  # ~2453 games; see derivation above


@dataclass(frozen=True)
class MoveOutcome:
    label: str
    wins: int
    draws: int
    losses: int

    @property
    def total(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def win_rate(self) -> float | None:
        if self.total == 0:
            return None
        return self.wins / self.total

    @property
    def score(self) -> float | None:
        if self.total == 0:
            return None
        return (self.wins + 0.5 * self.draws) / self.total

    @property
    def low_confidence(self) -> bool:
        return self.total < MIN_SAMPLE_SIZE


def _per_game_score_variance(outcome: MoveOutcome) -> float:
    """Var(X) for the per-game outcome random variable X in {0, 0.5, 1}.

    Derivation: with p_win/p_draw/p_loss the empirical proportions and
    mean = score = p_win*1 + p_draw*0.5 + p_loss*0, the variance of X about
    its own mean is, by definition,

        Var(X) = p_win*(1-mean)^2 + p_draw*(0.5-mean)^2 + p_loss*(0-mean)^2

    This is NOT the binomial variance p(1-p): treating "score" as a
    binomial proportion silently assumes every game is a hard win/loss,
    which double-counts draws' contribution to spread (a draw-heavy 50%
    scorer is actually less variable game-to-game than a decisive-heavy 50%
    scorer, and this formula reflects that while p(1-p) does not).
    """
    n = outcome.total
    if n == 0:
        return 0.0
    mean = outcome.score
    p_win = outcome.wins / n
    p_draw = outcome.draws / n
    p_loss = outcome.losses / n
    return p_win * (1 - mean) ** 2 + p_draw * (0.5 - mean) ** 2 + p_loss * (0 - mean) ** 2


def score_variance(outcome: MoveOutcome) -> float | None:
    """Var(score-estimator) = Var(X) / n -- the quantity that shrinks as
    the sample grows, used directly for confidence intervals and the
    two-sample z-test below."""
    if outcome.total == 0:
        return None
    return _per_game_score_variance(outcome) / outcome.total


def score_standard_error(outcome: MoveOutcome) -> float | None:
    var = score_variance(outcome)
    return None if var is None else math.sqrt(var)


def score_confidence_interval(outcome: MoveOutcome, z: float = Z_95) -> tuple[float, float] | None:
    """Normal-approximation CI for score, using the correct three-outcome
    variance (see ``_per_game_score_variance``) rather than treating score
    as a binomial proportion. Valid via the CLT for reasonably large n;
    for very small n (below ``MIN_SAMPLE_SIZE``) callers should already be
    treating the estimate as low-confidence regardless of the CI width.
    """
    if outcome.total == 0:
        return None
    se = score_standard_error(outcome)
    mean = outcome.score
    lo, hi = mean - z * se, mean + z * se
    return max(0.0, lo), min(1.0, hi)


def wilson_interval(p: float, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a true binomial proportion ``p`` estimated
    from ``n`` trials. Kept as a general-purpose utility (e.g. for a move's
    *popularity share*, which really is a binomial proportion) -- NOT used
    for score itself, see ``score_confidence_interval``.
    """
    if n == 0:
        return (0.0, 1.0)
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return max(0.0, lo), min(1.0, hi)


def is_significantly_different(a: MoveOutcome, b: MoveOutcome, z: float = Z_95) -> bool:
    """Two-sample z-test comparing expected scores, using the correct
    three-outcome variance (``score_variance``) for each side's standard
    error rather than the binomial ``p(1-p)/n``. Fast analytic cross-check
    to the bootstrap test in ``compare_moves``; returns False whenever
    either side has zero games.
    """
    if a.total == 0 or b.total == 0:
        return False
    se = math.sqrt(score_variance(a) + score_variance(b))
    if se == 0:
        return a.score != b.score
    return abs(a.score - b.score) > z * se


@dataclass(frozen=True)
class BootstrapComparison:
    observed_diff: float  # a.score - b.score
    ci_lo: float
    ci_hi: float
    p_value: float  # two-sided, from the bootstrap null (resampled diffs vs. 0)
    n_boot: int


def bootstrap_score_difference(
    a: MoveOutcome,
    b: MoveOutcome,
    n_boot: int = 10000,
    seed: int | None = None,
) -> BootstrapComparison | None:
    """Bootstrap the difference in score between two moves directly from
    their reported W/D/L counts, rather than assuming normality.

    Why bootstrap from the counts (endorsed as a valid choice in the
    project brief) instead of a parametric test: the Opening Explorer API
    only ever gives us aggregate W/D/L counts, never individual games, so
    "resampling from the counts" means redrawing each move's (wins, draws,
    losses) from Multinomial(n, [p_win, p_draw, p_loss]) -- the maximum-
    entropy generative model consistent with what we actually observed.
    This makes no CLT/normality assumption on the difference, which matters
    because deep-tree nodes at extreme rating bands often have exactly the
    small, skewed samples where the normal approximation is weakest.

    Returns None if either side has zero games (undefined score).
    """
    if a.total == 0 or b.total == 0:
        return None
    rng = np.random.default_rng(seed)
    p_a = np.array([a.wins, a.draws, a.losses]) / a.total
    p_b = np.array([b.wins, b.draws, b.losses]) / b.total

    draws_a = rng.multinomial(a.total, p_a, size=n_boot)  # (n_boot, 3): [win, draw, loss]
    draws_b = rng.multinomial(b.total, p_b, size=n_boot)

    scores_a = (draws_a[:, 0] + 0.5 * draws_a[:, 1]) / a.total
    scores_b = (draws_b[:, 0] + 0.5 * draws_b[:, 1]) / b.total
    diffs = scores_a - scores_b

    observed_diff = a.score - b.score
    ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])

    # Two-sided bootstrap p-value: recenter the resampled null on 0 (it's
    # already centered near observed_diff since we resampled around the
    # point estimates, so shift by observed_diff to get the null
    # distribution of the diff under "true difference = 0"), then ask how
    # often |null diff| >= |observed diff|.
    null_diffs = diffs - observed_diff
    p_value = float(np.mean(np.abs(null_diffs) >= abs(observed_diff)))
    p_value = max(p_value, 1.0 / n_boot)  # bootstrap can't resolve p below 1/n_boot

    return BootstrapComparison(
        observed_diff=float(observed_diff),
        ci_lo=float(ci_lo),
        ci_hi=float(ci_hi),
        p_value=p_value,
        n_boot=n_boot,
    )


@dataclass(frozen=True)
class ComparisonResult:
    z_test_significant: bool
    bootstrap: BootstrapComparison | None


def compare_moves(
    a: MoveOutcome, b: MoveOutcome, n_boot: int = 10000, seed: int | None = None
) -> ComparisonResult:
    """Run both comparison methods and return them together, so callers can
    report the primary (bootstrap) result while cross-checking against the
    analytic z-test."""
    return ComparisonResult(
        z_test_significant=is_significantly_different(a, b),
        bootstrap=bootstrap_score_difference(a, b, n_boot=n_boot, seed=seed),
    )


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> tuple[list[bool], list[float]]:
    """Benjamini-Hochberg step-up FDR correction.

    Why this matters: running k independent tests at alpha=0.05 each gives
    an expected 0.05*k false positives even when every null hypothesis is
    true -- with the hundreds of position x band x speed comparisons this
    project runs, a handful of "significant" divergences are guaranteed to
    be noise if we just eyeball raw p-values. BH controls the *expected
    proportion* of false discoveries among the rejected hypotheses (as
    opposed to Bonferroni, which controls the probability of *any* false
    positive at the cost of much lower power) -- an appropriate trade-off
    here since we'd rather tolerate a bounded, known error rate among
    "divergence found" claims than miss most real ones.

    Returns (reject_flags, adjusted_p_values), both in the *original* input
    order. adjusted_p_values[i] <= alpha iff reject_flags[i] is True.
    """
    m = len(p_values)
    if m == 0:
        return [], []
    indexed = sorted(range(m), key=lambda i: p_values[i])
    sorted_p = [p_values[i] for i in indexed]

    # Raw BH-adjusted p-value (q-value) at each rank, then enforce
    # monotonicity by taking a running minimum from the largest rank down.
    raw_adjusted = [sorted_p[k] * m / (k + 1) for k in range(m)]
    adjusted_sorted = [0.0] * m
    running_min = 1.0
    for k in range(m - 1, -1, -1):
        running_min = min(running_min, raw_adjusted[k])
        adjusted_sorted[k] = min(running_min, 1.0)

    adjusted = [0.0] * m
    for rank, orig_i in enumerate(indexed):
        adjusted[orig_i] = adjusted_sorted[rank]

    reject = [adj <= alpha for adj in adjusted]
    return reject, adjusted


def confident_ranking(
    outcomes: list[MoveOutcome], min_sample_size: int = MIN_SAMPLE_SIZE
) -> list[MoveOutcome]:
    """Sort outcomes by score, descending, but only among those meeting the
    minimum sample size. Outcomes below the threshold are dropped -- callers
    that want to display them anyway should say so explicitly, flagged as
    low-confidence.
    """
    eligible = [o for o in outcomes if o.total >= min_sample_size]
    return sorted(eligible, key=lambda o: o.score, reverse=True)
