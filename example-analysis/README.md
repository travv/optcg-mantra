# Example analyses

A small family of analyses that read parsed OPBounty replays out of
`$MANTRA_VAULT_ROOT` and emit markdown reports.

The first script (`kalgara-vs-teach-5don-turns.py`) is the original
self-contained worked example — read it first to see the end-to-end
pattern (load → filter → signature → group → render with thumbnails).

The newer scripts (`g1-…`, `c2-…`, `b2-…`) reuse a shared kernel under
[`mantra/analyzer/`](../mantra/analyzer/) so they stay small and consistent.
Use whichever style you prefer when adapting.

| Script | What it answers |
|---|---|
| `kalgara-vs-teach-5don-turns.py` | What does Kalgara do on its 5-DON turn vs Teach? (turn-N decision study, single matchup) |
| `g1-loss-replay-matcher.py` | For each LOSS in my personal game log, what are 3 top-MMR winning replays of the same matchup + turn order? |
| `c2-tech-adoption-trend.py` | Per leader, what cards are climbing or dropping in top-MMR decklists week over week? |
| `b2-pivotal-turn-detector.py` | For one losing replay, on which turn did the loser's win probability collapse — and what did winners play from the same state? |

## Reproduce — Kalgara 5-DON example

1. **Pull the sample** (a few hundred replays is plenty):
   ```
   snapshot_replays(leader="OP08-098", opponent="OP16-080", game_mode="0", limit=300)
   ```
   This caches `.log` + parsed `.json` into
   `$MANTRA_VAULT_ROOT/OP08-098-vs-OP16-080/`.

2. **Run the script:**
   ```bash
   python3 kalgara-vs-teach-5don-turns.py
   ```
   It reads every `.json` in the matchup folder, walks Kalgara's
   `don_at_start==5` turns, groups by action signature, and writes
   `kalgara-vs-teach-5don-turns.md` alongside.

### What the kalgara script does

- Filters to turns where the Kalgara player has 5 DON at turn start.
- Builds a short signature (`deploy:<id> · attach_don:<qty>->… · attack:LEADER · …`).
- Groups, counts wins/losses, also splits 1st-going vs 2nd-going.
- Tallies per-card play frequency + win rate for the turn.

### What's worth adapting

- The set of action verbs in `DROP_VERBS` — what counts as "bookkeeping" vs
  a real decision differs by leader.
- `tuple(sig[:5])` — first 5 tokens is enough for openings; bump higher for
  full-turn signatures.
- The 1st/2nd split — for second-going analysis, swap `don_at_start == 5`
  to `4` or `6` (see the DON-ramp gotcha in `../MANTRA.md`).

## Run the newer family

The G1 / C2 / B2 scripts share the same kernel and the same env-var setup;
each one takes `--help`. They all need `MANTRA_VAULT_ROOT` set.

### G1 — game log loss matcher

For a markdown game-log table (Date | Time | My Deck | Opponent | Result |
Roll | Order | …), find winning replays of the same matchup + orientation
from the corpus and emit an obsidian-friendly sidecar.

```bash
MANTRA_VAULT_ROOT=~/replays python3 g1-loss-replay-matcher.py \
    --games-md path/to/games.md \
    --out      path/to/games-study.md
```

Rows where the opponent leader id can't be parsed from `(OPxx-yyy)` are
flagged but not matched. Missing matchups emit `snapshot_replays(...)`
hints so you know which corpus to pull.

### C2 — tech adoption time series

For one leader, walk every matchup folder under the vault root where that
leader appears, aggregate decklists week by week, and surface biggest
movers / new entrants / departures / per-card performance gap.

```bash
MANTRA_VAULT_ROOT=~/replays python3 c2-tech-adoption-trend.py OP08-098 \
    --out-dir ./tech-trends
```

Filters to flex slots (5%-95% inclusion) so always-4-of staples don't
drown the signal. Small-sample weeks are flagged inline.

### B2 — pivotal turn detector

For one losing replay, build a coarse `(turn, life, hand, board)` state
table from the matchup corpus, look up the loser's WP at each of their
turns, and identify the largest single-turn WP drop. Render the loser's
played line vs the top-3 winning alternatives from the same state.

```bash
MANTRA_VAULT_ROOT=~/replays python3 b2-pivotal-turn-detector.py \
    OP08-098 OP16-080 \
    --out-dir ./pivotal-turn \
    [--replay path/to/specific.json]
```

Without `--replay`, picks the first losing replay it finds — handy for
smoke-testing.

## Adapting via the shared kernel

The G1/C2/B2 scripts import from [`mantra/analyzer/`](../mantra/analyzer/):

- `replay_loader` — load parsed JSONs from a matchup folder; player↔leader helpers.
- `decklist` — parse the `winner_deck`/`loser_deck` strings.
- `matchup_lookup` — locate matchup folders under `$MANTRA_VAULT_ROOT`.
- `action_token` — verb-aware action → compact token serializer; main vs existing-board split.
- `assets` — card-art download + local cache.
- `render` — vault-mode HTML thumbnail strips + repo-mode plain text.

When writing a new analysis: copy a script that's the closest shape, then
swap the per-analysis logic (filter predicate, signature length, grouping
key). The kernel handles parsing, rendering and asset bootstrap.
