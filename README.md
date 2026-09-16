# Lichess Opening Win-Rate Divergence

Uses the [Lichess Opening Explorer API](https://lichess.org/api#tag/Opening-Explorer)
to measure how the empirically best chess opening reply changes across
rating bands, and ships a CLI that finds the best empirical reply to a
given opening at a given rating.

## ⚠️ API access note — read this first

This project was scoped assuming the Opening Explorer (`/lichess`,
`/masters`, `/player` on `explorer.lichess.org`) was fully public, no key
required. **That's no longer true.** As of some point in 2026 those
endpoints started requiring OAuth authentication:

- The live API returns `401 Authorization Required` for every
  unauthenticated request (verified directly against
  `https://explorer.lichess.ovh/lichess` and `/masters` — network access
  itself is fine, the endpoints just reject anonymous requests).
- The current spec at
  [`lichess-org/api`](https://github.com/lichess-org/api/blob/master/doc/specs/tags/openingexplorer/lichess.yaml)
  lists `security: [OAuth2: []]` on all three Opening Explorer routes.
- [`lila-openingexplorer` issue #323](https://github.com/lichess-org/lila-openingexplorer/issues/323)
  documents the same thing happening to other users starting ~March 2026:
  unauthenticated requests got `429`, then `401`; adding a personal token
  fixed it.

**To unblock data collection:**

1. Log into a Lichess account (any account — no special scope needed).
2. Generate a free personal access token at
   <https://lichess.org/account/oauth/token> (leave all scope checkboxes
   unchecked — the Opening Explorer requires *some* token, not a specific
   scope).
3. Copy `.env.example` to `.env` and set `LICHESS_TOKEN=<your token>`.
4. Run the pipeline (below). Never commit `.env` or the token anywhere —
   it's already in `.gitignore`.

Everything in this repo — the client, the data-collection pipeline, the
analysis, and the CLI — is fully built and unit-tested against mocked
responses, and is ready to run for real the moment a token is available.
Without one, `scripts/collect_data.py` and `scripts/counter_repertoire.py`
fail fast with this same explanation rather than silently producing empty
or fabricated output.

## Setup

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env and paste in your LICHESS_TOKEN
```

## Running the pipeline end to end

```bash
# 1. Collect data: walks the opening tree (4 first moves, a few plies deep
#    into the most popular replies), pulling Lichess win/draw/loss by
#    rating band plus masters-database stats for the same positions.
#    Responses are cached under data/raw/ — reruns only fetch what's new.
python scripts/collect_data.py --out data/processed/opening_tree.json

# 2. Analyze: flags where the best-scoring move changes by rating band,
#    where a popular move underperforms a less-popular one, and where
#    masters' main line's score diverges between the lowest and highest
#    Lichess bands. Writes data/processed/divergence_findings.json and
#    docs/findings_generated.md (concrete tables, real numbers).
python scripts/analyze_divergence.py

# 3. Ask a specific question: best empirical reply to an opening, at a
#    given rating, respecting sample-size confidence.
python scripts/counter_repertoire.py --rating 1400 --against "1. e4 e5"
```

See `docs/findings.md` for the write-up (methodology, honesty caveats,
and — once `collect_data.py` has been run with a valid token — the actual
numbers).

## Design decisions

- **Speed**: **blitz** is the primary time control — by far the largest
  sample size across every rating band on Lichess, so win-rate estimates
  are least noisy. A shallow **rapid** pass (first two plies only) is
  collected as a cross-check on whether headline findings are
  blitz-specific.
- **"Win rate" = expected score**: ranking uses
  `(wins + 0.5 × draws) / total` — the standard chess convention for
  evaluating a move — not raw `wins / total`, because a move that draws
  80% of the time and rarely loses is clearly better than one with a
  slightly higher raw win rate but a much higher loss rate. Raw win rate
  is also reported alongside score everywhere. See
  `src/opening_divergence/stats.py`.
- **Sample-size confidence**: moves with fewer than `MIN_SAMPLE_SIZE`
  (default 30) games are flagged `low_confidence` and excluded from
  "best move" rankings by default; comparisons between two moves use a
  two-proportion z-test (`is_significantly_different`) rather than just
  comparing point estimates, so "5 games at 100%" never beats "5,000 games
  at 65%."
- **Rating bands**: the explorer's own buckets, 1000 through 2500+ (below
  1000 is excluded — too few serious games and too much rating noise to
  be a meaningful "low-rated" baseline).
- **Tree shape**: 4 first moves (1.e4, 1.d4, 1.Nf3, 1.c4) × top 3 replies
  × top 2 second moves — chosen to keep total API calls in the low
  hundreds (this is a rate-limited, "one request at a time" API) while
  still reaching a few plies into real opening theory. The *same*
  candidate moves are compared across all rating bands (branching choices
  are fixed from a single 1600 reference query) so that "how did the best
  move change" is a fair comparison of a fixed candidate set, not an
  artifact of different bands surfacing different candidates.
- **Caching & rate limiting**: `ExplorerClient` caches every successful
  response to `data/raw/<endpoint>/<hash>.json`, enforces a minimum delay
  between requests, and retries on `429`/`5xx` with exponential backoff
  (respecting `Retry-After` when present). Reruns of the pipeline never
  re-fetch a position already on disk.

## Project structure

```
src/opening_divergence/   # importable library (client, stats, tree, notation, repertoire, divergence)
scripts/                  # thin CLI wrappers: collect_data.py, analyze_divergence.py, counter_repertoire.py
data/raw/                 # cached raw API JSON (gitignored contents grow over time; kept out of git except .gitkeep)
data/processed/           # generated opening_tree.json / divergence_findings.json
docs/findings.md          # write-up: methodology + real findings once data is collected
tests/                    # pytest, all mocked/synthetic — no network access required
```

## Testing

```bash
pytest -q
ruff check .
```

All 31 tests are unit tests against mocked HTTP (`responses`) or synthetic
fixtures — they don't require a token or network access, and were run
clean before every commit in this repo's history.

## Honesty / limitations

- **Win rate ≠ objectively best move.** Popularity is a confound: a move
  played mostly by strong players will look artificially good in a
  high-rating bucket for reasons unrelated to the move itself (player
  skill, not move quality), and vice versa for a move that's a well-known
  trap against weaker opposition. This analysis reports what the data
  says, not a claim of objective opening truth.
- **Sample size matters more than the headline win rate.** Every
  comparison in this report is gated by `MIN_SAMPLE_SIZE` and a
  significance test — see `docs/findings.md` for exactly which
  comparisons rest on small samples.
- **Rating bands are Lichess's own self-reported buckets**, not a
  controlled experiment; band composition (bots, sandbagging, provisional
  ratings) is not modeled.

## Next steps

- Once a token is supplied and `collect_data.py` has run for real, fill in
  `docs/findings.md` with the generated numbers (this is otherwise ready).
- Consider widening the tree (more first moves, one more ply) once real
  request counts against the live API are known, to stay comfortably
  within rate limits.
- The `rapid` cross-check is currently shallow (first two plies); could be
  extended to the full tree if findings turn out to be speed-sensitive.
