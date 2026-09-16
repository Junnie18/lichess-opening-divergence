# Findings: Opening Win-Rate Divergence Across Rating Bands

**Status: pending real data collection.** The Lichess Opening Explorer API
now requires an OAuth token (see the README's "API access note") that this
session does not have — a Lichess account login is required to generate
one, which only a human can do. Every piece of code needed to produce this
report is written, unit-tested, and ready; running
`python scripts/collect_data.py && python scripts/analyze_divergence.py`
with a valid `LICHESS_TOKEN` in `.env` will populate the sections below
with real numbers, no code changes required.

This document is the template those numbers land in, plus the methodology
and honesty caveats that apply regardless of what the numbers turn out to
be.

## Methodology (fixed regardless of results)

- **Data source**: [Lichess Opening Explorer](https://lichess.org/api#tag/Opening-Explorer)
  (`explorer.lichess.org`), `/lichess` (rated games from all Lichess
  players) and `/masters` (master-level games), queried live and cached
  to `data/raw/`.
- **Speed**: blitz (primary — largest sample sizes across all rating
  bands), with a shallow rapid cross-check on the first two plies.
- **Rating bands**: 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500 (each
  covering up to the next boundary; 2500 is "2500 and above").
- **Opening tree**: 1.e4, 1.d4, 1.Nf3, 1.c4, each expanded into its top 3
  replies (by popularity in the 1600 band, used as a fixed reference so
  the same candidate moves are compared across every band), each further
  expanded into White's top 2 second moves.
- **"Score"**: `(wins + 0.5 × draws) / total`, White's expected points per
  game — the standard chess convention, not raw win rate (see README).
- **Confidence**: any move with fewer than 30 games in a given
  band/position is flagged low-confidence and excluded from "best move"
  claims. Comparisons between two candidate moves use a two-proportion
  z-test (95% level), not just a comparison of point estimates.

## 1. Does the "best" first move change across rating bands?

_Pending data. Will show, for each of 1.e4 / 1.d4 / 1.Nf3 / 1.c4, White's
score at every rating band, and flag if the ranking among them flips
between the lowest and highest bands._

## 2. Concrete divergence examples: popular ≠ best

_Pending data. Will list specific positions (exact move sequence) where
the most-played reply at a given rating band has a statistically
significantly worse score than a less-popular alternative at the same
band — with real sample sizes (n) and score deltas, not rounded
generalities._

## 3. Does master-level theory hold up in the lower-rated pool (or vice versa)?

_Pending data. Will list positions where the masters' database's
most-played move's score at the 1000+ Lichess band diverges sharply
(with sample sizes) from its score at the 2500+ band — i.e. cases where
"book theory" either doesn't translate down, or turns out to already be
correct even for much weaker players._

## 4. Full generated tables

_`scripts/analyze_divergence.py` writes `docs/findings_generated.md` with
the complete machine-generated tables (all positions, not just the
headline examples above) — link/inline it here once it exists._

## Honesty notes (apply to any numbers that eventually fill this in)

- **Popularity is a confound.** A move being "good" at 2200+ partly
  reflects that strong players choose it and play the resulting positions
  well — not necessarily that the move itself is intrinsically strong
  against equal-skill opposition at every level. Likewise, a move can look
  artificially bad at 1000-1200 because it leads to sharp, easily
  mishandled positions that punish weaker play regardless of the move's
  objective merit.
- **Small samples will be called out explicitly, inline**, not hidden in
  an average. Any comparison resting on a sample below `MIN_SAMPLE_SIZE`
  (30 games) is marked low-confidence and excluded from ranking claims;
  any comparison between two moves that isn't statistically significant
  (per the z-test) will say so rather than declaring a winner.
- **Rating bands are self-reported Lichess buckets**, not a controlled
  study — provisional ratings, sandbagging, and bots are not filtered out
  by this analysis.
