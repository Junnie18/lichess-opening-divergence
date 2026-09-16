# Lichess Opening Win-Rate Divergence

Uses the [Lichess Opening Explorer API](https://lichess.org/api#tag/Opening-Explorer)
to measure how the empirically best chess opening reply changes across
rating bands, with out-of-sample validation, multiple-comparisons
correction, and adversarial self-checks — not just point estimates. See
`docs/findings.md` for the full research write-up (methodology, results
with confidence intervals, robustness checks, limitations).

## Setup

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env and paste in your LICHESS_TOKEN
```

A personal access token is required (the Opening Explorer stopped serving
anonymous requests in 2026; see [`lila-openingexplorer` issue #323](https://github.com/lichess-org/lila-openingexplorer/issues/323)).
Generate one for free at <https://lichess.org/account/oauth/token> — no
scopes need to be checked.

## Running the pipeline end to end

```bash
# 1. Collect data: BFS-expands a 408-position opening tree (12 named
#    seeds -- e4/d4/Nf3/c4 plus Sicilian/French/Caro-Kann/Ruy Lopez/
#    Italian/Queen's Gambit/King's Indian-Grunfeld/English -- popularity-
#    pruned, 4-5 plies each), and pulls Lichess win/draw/loss stats by
#    rating band, speed, and TWO non-overlapping time windows (discovery
#    2016-01..2022-12, validation 2023-01..2026-08), plus masters-database
#    stats and a placebo sub-window pair for calibration. Responses are
#    cached under data/raw/ -- safe to interrupt and resume.
#    Takes several hours (~14k API requests at the client's 1 req/s
#    throttle); use --dry-run first to see the tree size and request
#    budget before committing.
python scripts/collect_data.py --dry-run
python scripts/collect_data.py

# 2. Analyze the discovery window: builds every "is move A better than
#    move B" comparison (best-move-shift-by-rating, popular-vs-better,
#    masters-vs-Lichess-pool), bootstraps a p-value for each, and applies
#    ONE Benjamini-Hochberg FDR correction across the whole family.
python scripts/analyze_divergence.py

# 3. The centerpiece: re-test every FDR-significant discovery finding
#    against validation-window data (same position/speed/bands/moves,
#    later time period) and report the replication rate honestly.
python scripts/validate_findings.py

# 4. Adversarial self-checks (see docs/findings.md for results):
python scripts/cross_speed_check.py     # do findings hold in rapid/classical?
python scripts/placebo_check.py         # is the significance test well-calibrated?
python scripts/sensitivity_check.py     # stable across threshold choices?
python scripts/concentration_check.py   # driven by one narrow line, or broad-based?

# 5. Ask a specific question: best empirical reply to an opening, at a
#    given rating, respecting sample-size confidence.
python scripts/counter_repertoire.py --rating 1400 --against "1. e4 e5"
```

## Design decisions

- **Metric**: expected score `(wins + 0.5 × draws) / total`, not raw win
  rate — the standard chess convention. Its confidence interval and
  standard error use the CORRECT three-outcome (win/draw/loss) variance
  formula, not a binomial `p(1-p)/n` approximation (see
  `src/opening_divergence/stats.py`'s `_per_game_score_variance` docstring
  for the derivation).
- **Two-sample comparisons**: bootstrapped directly from the reported
  W/D/L counts (`Multinomial(n, [p_win, p_draw, p_loss])` resampling),
  cross-checked against an analytic z-test using the same corrected
  variance. See `bootstrap_score_difference`/`compare_moves`.
- **Multiple comparisons**: with hundreds of positions × 8 rating bands ×
  3 speeds × 2 windows, running every comparison at raw alpha=0.05 would
  produce a guaranteed stream of false positives. Every script that builds
  a "finding family" applies Benjamini-Hochberg FDR correction across that
  whole family and reports both raw and FDR-adjusted significance.
- **Minimum sample size**: derived from an actual power calculation (80%
  power, alpha=0.05, 4-percentage-point effect size, conservative
  per-game variance 0.25) — `MIN_SAMPLE_SIZE ≈ 2453` games, not a round
  number. See `required_sample_size_per_group`.
- **Out-of-sample validation**: the opening tree's *structure* (which
  positions/moves to even look at) is fixed from discovery-window
  popularity only; validation-window data is used exclusively to re-test
  claims already made in discovery, never to pick new ones.
- **Adversarial checks**: placebo/null calibration (do false positives
  occur at ~alpha on genuinely-null comparisons?), threshold sensitivity
  (3×3 grid over min-sample-size and rating-band span), and
  concentration/outlier checks (is a recommendation broad-based or driven
  by one narrow opponent line?) — see `docs/findings.md` for results,
  including anything that did NOT hold up.
- **Caching & rate limiting**: `ExplorerClient` caches every successful
  response to `data/raw/<endpoint>/<hash>.json`, enforces a minimum delay
  between requests, and retries on `429`/`5xx` with exponential backoff.
  Reruns never re-fetch a position already on disk, so any script here is
  safe to interrupt and resume.

## Project structure

```
src/opening_divergence/   # importable library: client, stats, tree_builder, divergence, placebo,
                           # concentration, validate, repertoire, notation
scripts/                   # collect_data, analyze_divergence, validate_findings, cross_speed_check,
                           # placebo_check, sensitivity_check, concentration_check, counter_repertoire
data/raw/                  # cached raw API JSON (gitignored contents; kept out of git except .gitkeep)
data/processed/            # generated opening_tree.json + every *_results.json / *_findings.json
docs/findings.md           # the research write-up: methodology, results, robustness, limitations
tests/                     # pytest, all mocked/synthetic -- no network access required
```

## Testing

```bash
pytest -q
ruff check .
```

Every statistics/analysis module (variance/CI derivation, bootstrap
comparison, FDR correction, power calculation, tree builder, placebo
calibration, concentration/HHI, cross-window lookup) is unit-tested
against hand-computed or synthetic fixtures — no network access required.

## Honesty / limitations

See `docs/findings.md`'s Limitations section for the full discussion
(rating-band self-selection, provisional ratings, bots, engine-assisted
cheating rates, popularity-as-confound, and what the placebo/sensitivity/
concentration/replication checks did and did not confirm).
