# Progress checkpoint

Last updated: 2026-09-17 ~05:00 EDT.

## Done

- Data collection finished: 408/408 positions, `data/processed/opening_tree.json`
  written (22,766 requests this run + 2,321 cache hits).
- Full analysis chain run:
  - `scripts/analyze_divergence.py` -> `discovery_findings.json`
  - `scripts/validate_findings.py` -> `validation_results.json`
  - `scripts/cross_speed_check.py` -> `cross_speed_results.json`
  - `scripts/placebo_check.py` -> `placebo_results.json`
  - `scripts/sensitivity_check.py` -> `sensitivity_results.json`
  - `scripts/concentration_check.py` -> `concentration_results.json` (1,969
    live queries, run synchronously to completion; 510/1,969 = 25.9% flagged
    as concentration risk, see `docs/findings.md`)
- **Bug found and fixed mid-pipeline**: `best_move_shift_findings` in
  `src/opening_divergence/divergence.py` didn't enforce `min_n` on both
  sides of a comparison at the band actually being evaluated (only at
  each move's own band) — let n=1 samples through with spuriously tight
  bootstrap CIs. Fixed, regression test added
  (`tests/test_divergence.py::test_best_move_shift_requires_min_n_on_both_sides_at_eval_band`),
  and the entire analysis chain above was rerun against the fix. Details
  and before/after numbers in `docs/findings.md`'s Robustness section.
- Also fixed `scripts/sensitivity_check.py`'s "robust across all 9 grid
  cells" statistic, which was structurally unreachable by construction
  (a Finding's identity bakes in literal band values, which differ
  across the 3 band-span settings, so no finding could ever appear in
  more than 3/9 cells). Now reports min-n robustness (max 3) correctly
  and separately reports band-span comparison-pool-size effects.
- `scripts/counter_repertoire.py` sanity-checked live against the
  current API (both the confident-ranking path and the low-sample-size
  warning path) — works correctly.
- `docs/findings.md` fully written: Abstract, Results, Robustness &
  Adversarial Checks (including the concentration/outlier check, filled
  in last once `concentration_results.json` existed), Conclusion all
  filled in with real numbers, CIs, and p-values from the corrected
  pipeline output.

## Not yet started

Nothing — this checkpoint file is being committed alongside the final
commit that includes the concentration results, the completed
findings.md, and passing tests/lint (verified in this same session
before commit).
