# Progress checkpoint

Last updated: 2026-09-16 ~14:05 EDT (data collection in progress).

## Done

- `LICHESS_TOKEN` verified working live; dotenv fix committed.
- All engineering complete and pushed to `origin/main`:
  - `src/opening_divergence/client.py` — since/until date-range support
    (lichess: YYYY-MM month strings; masters: YYYY year ints — different
    formats, confirmed against the live API after a 400).
  - `src/opening_divergence/stats.py` — corrected 3-outcome variance for
    score CIs, bootstrap two-sample comparison, Benjamini-Hochberg FDR,
    power-calculation-derived `MIN_SAMPLE_SIZE` (~2453).
  - `src/opening_divergence/tree_builder.py` — popularity-pruned BFS tree
    construction from named seeds.
  - `src/opening_divergence/divergence.py` — Finding dataclass + 3 finding
    types (best_move_shift, popularity_gap, master_theory), all bootstrap-
    backed, p-values computed but significance NOT decided per-finding
    (that's the caller's job once the whole family is known).
  - `src/opening_divergence/placebo.py`, `concentration.py`, `validate.py`
    — library logic for the three adversarial checks + cross-window
    lookup, all unit-tested against synthetic fixtures.
  - `scripts/collect_data.py` — builds the 408-position tree (dry-run
    verified) and collects: blitz × 8 bands × {discovery, validation};
    rapid/classical × 8 bands × discovery-only; masters (single window
    spanning both eras); placebo (2 adjacent discovery months, reference
    band). ~14,280 requests total at the client's 1 req/s throttle.
  - `scripts/analyze_divergence.py` — discovery-window finding family +
    one BH correction across the whole family.
  - `scripts/validate_findings.py` — re-tests FDR-significant discovery
    findings against validation-window data (direction + significance +
    its own BH correction required to count as "replicated").
  - `scripts/cross_speed_check.py` — same headline findings re-tested
    against rapid/classical discovery-window data.
  - `scripts/placebo_check.py` — null-calibration check (adjacent-month
    comparisons; reports observed false-positive rate vs. nominal alpha).
  - `scripts/sensitivity_check.py` — 3×3 grid (min-n × rating-band span)
    robustness check.
  - `scripts/concentration_check.py` — HHI-based outlier check on
    headline popularity-gap recommendations (one extra live query each).
  - 71 unit tests, all passing; `ruff check .` clean.
  - `README.md` rewritten for the new pipeline.
  - `docs/findings.md` — Methodology and Limitations sections are FINAL
    and written; Abstract/Results/Robustness/Conclusion are placeholders
    pending real numbers.

## In flight

- **`scripts/collect_data.py` is running in the background** (detached
  process, NOT harness-tracked — was launched via `nohup ... & disown`
  from a backgrounded Bash call that itself already exited, so no
  automatic completion notification will arrive; must be checked
  manually). Started ~13:52 EDT. Log: `logs/collect_data.log`.
  Progress as of last check: ~6-10/408 positions, pacing ~70-90s/node
  (slower than the initial 35s/node estimate — likely network latency;
  not investigated further since it's well within tolerance). At that
  pace, expect **~7-9 hours total**, i.e. completion roughly 21:00-23:00
  EDT on 2026-09-16.
  - **If the process has died** (check with
    `ps aux | grep collect_data.py`): just rerun
    `python scripts/collect_data.py --out data/processed/opening_tree.json
    --cache-dir data/raw` — every completed request is cached to
    `data/raw/`, so this resumes cheaply rather than restarting from
    scratch. Check `logs/collect_data.log`'s tail for a traceback first;
    the one crash so far (masters since/until format) is already fixed.

## Not yet started (blocked on data collection finishing)

1. Run `scripts/analyze_divergence.py` → `data/processed/discovery_findings.json`.
2. Run `scripts/validate_findings.py` → `data/processed/validation_results.json`.
3. Run `scripts/cross_speed_check.py` → `data/processed/cross_speed_results.json`.
4. Run `scripts/placebo_check.py` → `data/processed/placebo_results.json`.
5. Run `scripts/sensitivity_check.py` → `data/processed/sensitivity_results.json`.
6. Run `scripts/concentration_check.py` → `data/processed/concentration_results.json`.
7. Fill in `docs/findings.md`'s Abstract/Results/Robustness/Conclusion
   sections with the real numbers from the above (every claim needs an n
   and a CI or p-value next to it — no bare point estimates).
8. Sanity-check `scripts/counter_repertoire.py` still works end-to-end
   against live data (it doesn't depend on the tree/collected data at
   all — makes its own live query — so should be unaffected, but hasn't
   been re-run live since the MIN_SAMPLE_SIZE default changed to ~2453).
9. Final full `pytest -q` + `ruff check .`, commit everything, push.
10. Send a final push notification summarizing the headline result and
    replication rate.

## Resume instructions for a follow-up session

```bash
cd ~/lichess-opening-divergence
tail -50 logs/collect_data.log        # check collection status
ps aux | grep collect_data.py         # is it still running?
# if finished (log ends with "Wrote data/processed/opening_tree.json..."):
python scripts/analyze_divergence.py && \
python scripts/validate_findings.py && \
python scripts/cross_speed_check.py && \
python scripts/placebo_check.py && \
python scripts/sensitivity_check.py && \
python scripts/concentration_check.py
# then fill in docs/findings.md's placeholder sections with the results.
```
