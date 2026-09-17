# Findings: Opening Win-Rate Divergence Across Rating Bands

**Status: complete.** Data collection (408 positions), the full analysis
chain, and all four adversarial checks have run against live Lichess
Explorer data. See `PROGRESS.md` for the run log.

## Abstract

Across 408 opening positions and three finding types (best-move shift by
rating, popularity/skill gaps, and master-theory-vs-amateur-score gaps),
the discovery-window family produced 2,837 testable comparisons, of which
2,410 (84.9%) were significant after Benjamini-Hochberg FDR correction at
alpha=0.05. Of those 2,410 headline findings, 2,351 (97.6%) had enough
validation-window (2023-01 through 2026-08) data to re-test, and 2,060 —
**87.6%** (95% Wilson CI [86.2%, 88.9%], n=2,351) — replicated: same
direction, raw p<0.05, and its own independent FDR correction. A further
232 (9.9%) matched direction but lost significance out-of-sample, and 59
(2.5%) flipped direction entirely. Findings are far more speed-specific
than time-specific: replication against same-window rapid data is only
69.4% (1,628/2,346) and against classical only 44.5% (993/2,230) — a
sizeable share of blitz divergences are blitz-specific, not universal
across time controls. The placebo check (adjacent discovery-period
months, no real signal expected) found a raw false-positive rate of
5.54% (95% CI [4.70%, 6.52%], n=2,454) against a 5% nominal alpha — the
pipeline is well-calibrated — and 0/2,454 survive FDR correction, as
expected under a true null. Threshold sensitivity is the weakest link:
of 650 headline findings at the baseline threshold (rating bands
1000/2500), only 399 (61.4%) stay significant across a 0.5x-2x sweep of
the minimum-sample-size cutoff; changing which two rating bands anchor
the comparison changes the pool of testable comparisons substantially
(849 to 1,403 across the grid), so band-span choice is not a small
perturbation. A concentration/outlier check on all 1,969 headline
popularity-gap ("counter-repertoire") recommendations found 510 (25.9%,
95% CI [24.0%, 27.9%]) are concentration risks — the recommended move's
score is driven mostly by one specific opponent reply rather than a broad
spread — rising from 14.4% at the 1000 band to 49.4% at 2500+; full
breakdown in Robustness below. One methodological finding surfaced along the way and
is worth stating plainly: an early version of the best-move-shift check
did not enforce the minimum-sample-size threshold on both sides of a
cross-band comparison, letting a handful of single-game samples produce
spuriously tight bootstrap confidence intervals; this was caught,
fixed (`src/opening_divergence/divergence.py`), covered by a regression
test, and all downstream results here reflect the corrected pipeline (see
Robustness for the before/after numbers).

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

All numbers below are from the discovery window (2016-01 through
2022-12), blitz speed unless stated otherwise, 408 positions,
`MIN_SAMPLE_SIZE=2453` (see Methodology). Full family: **2,837**
comparisons, **2,425** raw-significant (p<0.05), **2,410** FDR-significant
after one Benjamini-Hochberg pass across the whole family (15
raw-significant comparisons did not survive correction).

| Finding type | Comparisons | Raw-sig. | FDR-sig. |
|---|---|---|---|
| popularity_gap (popular move underperforms a less-popular one) | 2,267 | 1,979 | 1,969 |
| best_move_shift (confident-best move differs by rating band) | 334 | 263 | 260 |
| master_theory (masters' top move's score differs low vs. high band) | 236 | 183 | 181 |

### Headline examples

**popularity_gap** — 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 Bc5 5. Nxf7
(the Traxler/Wilkes-Barre counterattack, White grabs f7). At the 1000
band, **O-O** (n=3,934) outscores the far more popular **Bxf2+**
(n=72,457) by **+0.521** score (95% CI [0.512, 0.529], FDR-adjusted
p=1.4e-4) — the immediate discovered-check grab that looks natural is
empirically much worse than the quiet king safety move. This matches
established Traxler theory (O-O keeps the attack going without giving
White's king an escape square) and **replicated** in the validation
window.

**best_move_shift** — 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 (Fried Liver
Attack setup). At the 1000 band, the confident-best reply is **Be7**
(n=16,127, score reflects avoiding the sac lines) vs. the far more
popular **d5** (n=842,546, walking into 4...d5 5.exd5 Nxd5 6.Nxf7!), a
**+0.326** gap (95% CI [0.321, 0.330], p=1.4e-4), **replicated**. A
concrete, well-known practical trap showing up cleanly in the data.

**master_theory** — 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 b5 (Ruy Lopez).
Masters' top move **Bb3** scores **0.096 lower** (95% CI [-0.111,
-0.081], p=1.4e-4) at the 2500+ band (n=3,937) than at the 1000 band
(n=201,054) — consistent with a well-known-theory move's edge shrinking
against stronger defense, rather than the move itself changing merit.
**Replicated.**

All three headline examples above replicated out of sample; see
Robustness for the full replication rate and the findings that did not.

## Robustness & Adversarial Checks

### A bug caught mid-pipeline

`best_move_shift_findings` originally checked that each candidate move
was "confident" (>= `MIN_SAMPLE_SIZE`) **at its own band**, but then
compared both moves' scores **at both bands** without re-checking the
sample size at the band actually being evaluated. That let through
comparisons like a move with **n=1** at the 2500 band being tested
against a move with thousands of games — and because the bootstrap
resamples from the empirical outcome distribution, an n=1 sample has
*zero* resampling variance (it can only ever reproduce the one game it
saw), so the resulting CI was artificially tight and the comparison came
out "significant." 59/318 (18.6%) of the original best_move_shift
headline findings had at least one side under the sample-size threshold.
Fixed by requiring `total >= min_n` on both sides at the evaluated band
(matching what `popularity_gap_findings` and `master_theory_findings`
already did correctly), with a regression test
(`tests/test_divergence.py::test_best_move_shift_requires_min_n_on_both_sides_at_eval_band`).
Effect: best_move_shift comparisons dropped from 510 to 334 (FDR-sig.
318 → 260); every number in this document reflects the fixed pipeline.
Flagging this here rather than silently fixing it, since it's exactly
the kind of failure the adversarial checks below are meant to catch —
this one happened to be caught by inspection instead.

### Out-of-sample replication

2,410 headline (FDR-significant) discovery findings; 2,351 (97.6%) had
enough validation-window (2023-01 – 2026-08) data to re-test. **2,060 /
2,351 = 87.6% replicated** (same direction, raw p<0.05, survives its own
independent FDR correction), 95% Wilson CI **[86.2%, 88.9%]**. Of the
rest: 232 (9.9%) matched direction but lost significance, and **59
(2.5%) flipped direction** — reported here rather than dropped, per
finding type:

| Type | Headline | Testable | Replicated | Rate (95% CI) |
|---|---|---|---|---|
| popularity_gap | 1,969 | 1,923 | 1,712 | 89.0% [87.6%, 90.3%] |
| best_move_shift | 260 | 247 | 194 | 78.5% [73.0%, 83.2%] |
| master_theory | 181 | 181 | 154 | 85.1% [79.2%, 89.5%] |

best_move_shift replicates noticeably worse than the other two types —
consistent with it being the type most exposed to per-move sample-size
sparsity even after the fix above (best-move comparisons are inherently
about rarer, band-specific move choices, not aggregate popularity).

### Cross-speed replication

Re-testing the same 2,410 headline findings against same-window
(discovery-period) rapid and classical data, not a different time
period — this asks "is this blitz-specific?" rather than "did it hold up
over time?":

- **Rapid**: 1,628 / 2,346 testable = **69.4%** (95% CI [67.5%, 71.2%])
- **Classical**: 993 / 2,230 testable = **44.5%** (95% CI [42.5%, 46.6%])

This is markedly weaker than the 87.6% out-of-sample (same-speed,
different-time) replication rate. Read plainly: a large share of these
divergences are real but **blitz-specific** phenomena (fast-time-control
decision-making, not universal opening truths) rather than being
artifacts of a particular time window. Classical in particular — the
format where players have the most time to find the objectively best
move — replicates well under half the time, which should temper any
claim that these findings generalize across time controls.

### Placebo calibration

2,454 null comparisons between two adjacent discovery-period months
(2021-06 vs. 2021-07, no real signal expected). Raw false-positive rate:
**136/2,454 = 5.54%** (95% CI [4.70%, 6.52%]) against a 5% nominal
alpha — the CI contains 5%, so the pipeline is **well-calibrated** at
the raw-p level. After FDR correction: **0/2,454 (0.00%)** false
positives, as expected under a true null. This is a meaningful sanity
check on the bootstrap + BH machinery itself, independent of anything
about chess.

### Threshold sensitivity

This is the weakest of the four checks. At the baseline threshold
(`min_n=2453`, rating bands 1000/2500), there are 650 headline findings.
Sweeping `min_n` at **0.5x/1x/2x** while holding the band span fixed,
**399/650 = 61.4%** (95% CI [57.6%, 65.1%]) stay FDR-significant at all
three multipliers; the other 251 (38.6%) are sensitive to exactly where
the sample-size bar is set.

Separately — and this is *not* a per-finding robustness comparison, see
below — changing which two rating bands anchor the comparison changes
how many comparisons even exist to test: 849 at the extreme span
(1000/2500), 1,288 at inward-1 (1200/2200), 1,403 at inward-2
(1400/2000), of which 650 / 1,095 / 1,175 are FDR-significant
respectively. **This growth is confounded with sample availability, not
just a rating-gap effect**: extreme bands (1000, 2500+) have far fewer
total players/games than the middle of the distribution, so more
comparisons fail the `min_n` bar outright at the extreme span (849
testable) than at the narrower spans (up to 1,403 testable). A specific
finding computed at bands 1000/2500 is, by construction, never "the same
comparison" as one computed at 1200/2200 — Lichess's rating bands are
disjoint categorical buckets, not a continuous axis — so there is no
meaningful per-finding "significant in all 9 grid cells" statistic to
report (an earlier draft of this script implied there was; that framing
was itself a bug in the check, corrected before these numbers were
produced — see `scripts/sensitivity_check.py`'s docstring for detail).

**Bottom line: ~39% of headline findings would not have cleared FDR
significance at a lower or higher min-n threshold, and the choice of
which two rating bands to compare has an even larger effect on which
comparisons are even testable.** Treat any single headline number in
this document as sitting on top of that variability, not as a
threshold-independent fact.

### Concentration / outlier check

For every FDR-significant popularity_gap recommendation ("play the
less-popular move Y instead of the popular move X"), one extra live query
fetches the position one ply after Y and computes the Herfindahl-Hirschman
Index (HHI) over the opponent's replies there (`src/opening_divergence/
concentration.py`, `scripts/concentration_check.py`). HHI ranges from
near-0 (opponents reply many different ways — Y's score is broad-based)
to 1 (opponents reply one way almost every time — Y's score is really the
score of one specific follow-up sub-line, a much weaker recommendation
since it collapses if the opponent doesn't cooperate). `HHI > 0.5` is
flagged as a concentration risk.

All 1,969 headline popularity_gap findings had a live child-position
sample (median 2,830+ games each, no position fell below 30 games, so
this isn't a small-sample artifact). **510 / 1,969 = 25.9%** (95% Wilson
CI [24.0%, 27.9%]) are concentration risks — median HHI across all 1,969
is 0.327 (IQR [0.231, 0.505]), and median dominant-reply share is 48.9%,
so the typical recommendation is *not* a single-line trap, but a
non-trivial quarter of them are.

Risk rate rises sharply and monotonically with rating band:

| Band | n | Risk | Rate |
|---|---|---|---|
| 1000 | 215 | 31 | 14.4% |
| 1200 | 263 | 43 | 16.3% |
| 1400 | 284 | 60 | 21.1% |
| 1600 | 307 | 76 | 24.8% |
| 1800 | 299 | 93 | 31.1% |
| 2000 | 286 | 91 | 31.8% |
| 2200 | 234 | 76 | 32.5% |
| 2500 | 81 | 40 | 49.4% |

Read plainly: at the 1000 band a recommended "better" move typically
holds up against a broad spread of opponent replies, but at 2500+ nearly
half the headline recommendations are really "this one line works well
against the one reply opponents actually play" — consistent with
higher-rated opponents converging on a narrower, more theory-informed set
of replies, which is exactly the condition under which a single reply can
dominate the sample. The most concentrated case in the dataset is 1. c4
e5 2. g3 Bc5 3. Nc3 Bxf2+ at the 1600 band (HHI=1.000, 100% of 2,830
games see one specific opponent reply); the broadest is 1. e4 Bc4 Nf6 3.
d3 d6 at the 1800 band (HHI=0.131 across 66,649 games). Several of the
most concentrated cases (e.g. ...Qa4+ against the Ragozin/QGD Bb4 lines
at 2500) are forcing checks with one natural blocking reply rather than
traps exploiting a mistake — concentration alone doesn't distinguish
"narrow trap" from "forcing move with one sound response," which this
check cannot tell apart from HHI alone; a reader should treat a flagged
finding as "verify the follow-up line yourself before trusting it as a
practical recommendation," not as "this finding is wrong."

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

The core claim survives scrutiny, with real caveats attached. Out-of-sample
replication is strong (87.6%, 95% CI [86.2%, 88.9%], n=2,351) and the
pipeline's own null-calibration check passes (5.54% raw false-positive
rate against a 5% nominal alpha, 0% after FDR correction) — this is not
noise dressed up as signal. But three of the five adversarial checks surface
real fragility that a reader should weigh before treating any single
headline number as load-bearing: findings are markedly less likely to
hold in classical time controls than blitz (44.5% vs. the 87.6%
same-speed replication rate), meaning a meaningful share of what's
labeled "opening theory divergence" here is really "blitz decision-making
divergence"; threshold choice matters more than one would like — 61.4%
of headline findings survive a 0.5x-2x sweep of the sample-size cutoff,
and the choice of which two rating bands to compare changes the testable
comparison pool by nearly 2x; and a quarter of counter-repertoire
recommendations (25.9%, rising to 49.4% at 2500+) lean on one specific
opponent reply rather than holding up broadly, so "this move scores
better" does not always mean "this move is robust regardless of how the
opponent responds" — particularly at high rating bands, where the
practical value of a "surprise" recommendation is most likely to be
overstated by a bare score comparison. The methodological bug caught and fixed
mid-pipeline (best_move_shift's missing cross-band sample-size check,
Robustness above) is itself a data point: an 18.6% contamination rate in
one finding type from a single missing bounds check is a reminder that
"FDR-significant" is only as trustworthy as every upstream sample-size
guarantee actually holding, and that adversarial checks earn their cost
by catching exactly this kind of thing. Net: treat the popularity-gap and
master-theory findings (the two types with the strongest replication and
the check least exposed to the fixed bug) as the more reliable half of
this dataset, and any specific best-move-shift or narrow-band-span claim
as provisional until checked against the finding's own CI and replication
status in the underlying JSON — not read off this document's headline
examples alone.
