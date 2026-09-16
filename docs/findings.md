# Findings: Opening Win-Rate Divergence Across Rating Bands

**Status: methodology finalized, data collection in progress.** This
document is being written incrementally as the pipeline runs; see
`PROGRESS.md` at the repo root if you're picking this up mid-run. The
Abstract, Results, Robustness & Adversarial Checks, and Conclusion
sections below are placeholders until `scripts/collect_data.py` and the
full analysis chain finish — everything else (Methodology, Limitations)
is final and does not depend on what the numbers turn out to be.

## Abstract

_Pending final data. Will summarize: how many of the discovery-window
FDR-significant findings replicated out-of-sample, the headline
divergence/counter-repertoire results with their confidence intervals,
and the outcome of the four adversarial checks, in 4-6 sentences._

## Methodology

### Data source

[Lichess Opening Explorer](https://lichess.org/api#tag/Opening-Explorer)
(`explorer.lichess.org`), `/lichess` (rated games across all Lichess
players, broken out by rating band and speed) and `/masters`
(master-level games), queried live with a personal access token (required
since 2026; see `README.md`) and cached to `data/raw/`.

### Opening tree

408 distinct positions, BFS-expanded from 12 named seeds using a
popularity-pruned branching rule (see `src/opening_divergence/tree_builder.py`
and `scripts/collect_data.py`):

- 4 bare first moves: 1.e4, 1.d4, 1.Nf3, 1.c4 (each expanded 5 plies deep)
- 8 systems anchored a few plies in, expanded 4 further plies each:
  Sicilian (1.e4 c5), French (1.e4 e6), Caro-Kann (1.e4 c6), Ruy Lopez
  (1.e4 e5 2.Nf3 Nc6 3.Bb5), Italian (1.e4 e5 2.Nf3 Nc6 3.Bc4), Queen's
  Gambit (1.d4 d5 2.c4 e6), King's Indian/Grunfeld complex (1.d4 Nf6 2.c4
  g6), English reversed-Sicilian (1.c4 e5)

At each ply, only the top 2 replies by popularity are expanded, and only
if they clear a 2%-of-games popularity-share threshold — this keeps the
tree tractable while still reaching genuine opening theory rather than
stopping after 1-2 moves. Branching decisions are fixed ONCE from
discovery-window reference data (1600 rating band, blitz) so the exact
same position/candidate-move set is queried across every rating band,
speed, and time window below; no window ever sees a different candidate
set than any other for the same position, which is what makes the
band/speed/window comparisons fair.

### Rating bands

The Opening Explorer's own buckets: 1000, 1200, 1400, 1600, 1800, 2000,
2200, 2500 (each running up to the next boundary; 2500 covers 2500+). The
API also offers a "0" band, which is cumulative from 0 rating and
therefore overlaps every other band rather than being a distinct
comparison point — excluded for the same reason the original scope did:
it isn't a meaningful standalone "low-rated" baseline.

### Speeds

**Blitz** is primary (by far the largest sample sizes across all rating
bands) and gets the full band × window matrix. **Rapid** and
**classical** are collected across the same 8 bands, discovery-window
only, as a same-window cross-speed check (`scripts/cross_speed_check.py`)
— a different question from out-of-sample replication (below): "is this
blitz-specific?" rather than "did it hold up over time?".

### Discovery / validation time-window split

The `/lichess` endpoint supports `since`/`until` month-range filters
(confirmed against the live API spec, not assumed). Two strictly
non-overlapping windows:

- **Discovery**: 2016-01 through 2022-12. Used for everything: choosing
  which positions/moves to even look at (tree structure), and every
  headline finding.
- **Validation**: 2023-01 through 2026-08. Used ONLY to re-test claims
  already made in discovery — never to discover new ones. This is the
  centerpiece rigor check (`scripts/validate_findings.py`): a finding
  "replicates" only if the same comparison, run on validation-window
  data, has the same direction, is significant at raw p<alpha, AND
  survives its own (separately-run) FDR correction.
- **Masters** data is scoped to since=2016/until=2026 (the same overall
  era as the rest of the study) rather than the API's full historical
  range back to 1952, so it isn't comparing modern amateur play against
  a completely different competitive era of top-level chess.

### Placebo sub-windows

Two adjacent months squarely inside the discovery period — 2021-06 and
2021-07 — used only by the placebo calibration check (below). Adjacent
months were chosen specifically to minimize genuine chess-"meta" drift
between the two samples, as opposed to comparing early- vs. late-discovery
(which would confound "the pipeline is miscalibrated" with "the actual
meta shifted over the years").

### Metric and its confidence interval

Expected score, `(wins + 0.5 × draws) / total` — the standard chess
convention for evaluating a move (a draw counts as half a point, not as a
discarded observation). Ranking uses score; raw win rate is reported
alongside it.

The metric is **not** a binomial proportion — a game's outcome is a
three-way categorical variable (win/draw/loss contributing 1/0.5/0 to the
mean), so its variance is derived from first principles rather than
approximated as `p(1-p)/n`:

```
Var(X) = p_win·(1 - mean)² + p_draw·(0.5 - mean)² + p_loss·(0 - mean)²
Var(score-estimator) = Var(X) / n
```

(`src/opening_divergence/stats.py::_per_game_score_variance`, unit-tested
against a hand-computed example in `tests/test_stats.py`). This matters:
two moves with identical score can have different variance depending on
how draw-heavy they are (a 50%-scorer via mostly draws is less volatile
game-to-game than a 50%-scorer via a 50/50 split of decisive results),
and the binomial approximation can't distinguish them.

Confidence intervals use the normal approximation with this corrected
variance: `score ± z·SE`.

### Two-sample comparisons

**Bootstrap**, resampling each side's (wins, draws, losses) from
`Multinomial(n, [p_win, p_draw, p_loss])` — the maximum-entropy generative
model consistent with the aggregate counts the API actually returns (it
never exposes individual games). 10,000 resamples per comparison by
default; reports the observed difference, a percentile bootstrap 95% CI,
and a two-sided p-value. Cross-checked against an analytic two-sample
z-test using the corrected variance above
(`opening_divergence.stats.compare_moves`); the two methods agree closely
in every comparison inspected during development, which is itself a
sanity check that neither has a implementation bug distorting results.

### Multiple-comparisons correction

Every analysis script that builds a family of comparisons (hundreds of
position × band × speed × window combinations) applies **Benjamini-
Hochberg FDR correction across that entire family** in one pass, and
reports both raw and FDR-adjusted significance
(`opening_divergence.stats.benjamini_hochberg`, unit-tested against a
hand-worked reference case). This matters because running k independent
tests at raw alpha=0.05 produces an expected 0.05k false positives even if
every null hypothesis were true; with the hundreds of comparisons this
project runs, eyeballing raw p-values would manufacture "divergences" out
of noise. BH controls the *expected proportion* of false discoveries
among the rejected hypotheses, trading some power (vs. no correction) for
a bounded, known error rate — a deliberate choice over the stricter
Bonferroni correction, which would control the probability of *any* false
positive but at a much larger power cost given the size of this family.

### Power-derived minimum sample size

`MIN_SAMPLE_SIZE` is derived from an actual power calculation rather than
a round number: 80% power to detect a 4-percentage-point score difference
at alpha=0.05, two-sided, equal group sizes, using a conservative
(variance-maximizing) per-game variance of 0.25:

```
n = 2 · (z_{alpha/2} + z_{power})² · σ² / δ²
  = 2 · (1.959964 + 0.841621)² · 0.25 / 0.04²
  ≈ 2453 games per side
```

This is dramatically higher than the 30-game threshold used in the prior
version of this project. The practical consequence — far fewer deep-tree
positions clear the bar, especially at extreme rating bands — is itself
reported honestly in Results/Robustness below, not hidden.

### Train/test discipline

To avoid information leakage between discovery and validation: (1) tree
structure (which positions exist at all) is fixed from discovery-window
popularity only; (2) which specific move-pairs get tested for "best move"
and "popularity gap" claims is decided from discovery-window data only;
(3) validation-window data is touched exactly once, to re-test the
already-fixed set of FDR-significant discovery claims — never to search
for new candidate findings. This mirrors standard train/test-split
discipline in predictive modeling, applied to a descriptive-statistics
pipeline where the analogous failure mode is "p-hacking via infinite
comparisons," not overfitting a model.

## Results

_Pending final data — see PROGRESS.md for pipeline status. Will report,
per finding type (best-move-shift, popularity-gap, master-theory), the
number of raw and FDR-significant comparisons out of the full family,
with concrete examples (position, moves, n, score, 95% CI, p-value,
FDR-adjusted p-value) for the headline cases._

## Robustness & Adversarial Checks

_Pending final data. Will report:_

- _Out-of-sample replication rate (scripts/validate_findings.py) —
  including findings that did NOT replicate, not just the ones that did._
- _Cross-speed replication (scripts/cross_speed_check.py) — do findings
  hold in rapid/classical, or are they blitz-specific?_
- _Placebo calibration (scripts/placebo_check.py) — observed false-
  positive rate on null (adjacent-month) comparisons vs. the nominal 5%,
  with a Wilson CI._
- _Threshold sensitivity (scripts/sensitivity_check.py) — how many
  headline findings are robust across all 9 cells of the min-sample-size
  × rating-band-span grid vs. fragile._
- _Concentration/outlier check (scripts/concentration_check.py) — for
  each headline counter-repertoire recommendation, whether its good score
  is broad-based across opponent replies or concentrated in one narrow
  line._

## Limitations

- **Popularity is a confound.** A move being "good" at a high rating band
  partly reflects that strong players choose it and navigate the
  resulting positions well — not necessarily that the move itself is
  intrinsically strong against equal-skill opposition at every level.
  Symmetrically, a move can look artificially bad at low bands because it
  leads to sharp positions that punish inexperience regardless of the
  move's objective merit. This analysis reports what the empirical data
  says, not a claim of objective opening truth.
- **Rating bands are self-reported Lichess buckets**, not a controlled
  experiment. Band composition is not adjusted for:
  - **Provisional ratings** — new accounts with unstable, sometimes wildly
    inaccurate ratings are included in whichever band they currently sit in.
  - **Bots** — Lichess's opening-explorer game pool is not guaranteed
    bot-free; a bot-heavy sub-population within a band would shift its
    statistics in ways unrelated to human play quality at that level.
  - **Sandbagging / smurfing** — players deliberately parked below their
    real strength are misclassified by band.
  - **Engine-assisted play** — Lichess bans detected cheaters, but
    detection is imperfect and lagged; some fraction of games in every
    band include undetected engine assistance, which would inflate scores
    for whatever moves engines currently favor.
- **Sample size still varies enormously by position.** Even with a
  power-derived threshold, root positions (1.e4, 1.d4) have orders of
  magnitude more games than a specific line 6 plies deep at the 2500+
  band — the sensitivity check quantifies how much this affects which
  findings survive threshold changes.
- **"Best" is score-only.** This analysis does not incorporate engine
  evaluation, opening theory novelty, or practical factors like how hard
  a line is to remember/play under time pressure — only the empirical
  score across games actually played.

## Conclusion

_Pending final data._
