# Example: Kalgara vs Teach — 5-DON turn analysis

A worked example of the standard "what does this leader do on turn N in this
matchup?" analysis. Use as a template — swap leader ids, swap the
`don_at_start` value, run.

## Reproduce

1. **Pull the sample** (a few hundred replays is plenty):
   ```
   snapshot_replays(leader="OP08-098", opponent="OP16-080", game_mode="0", limit=300)
   ```
   This caches `.log` + parsed `.json` into
   `$OPBOUNTY_VAULT_ROOT/OP08-098-vs-OP16-080/`.

2. **Run the script:**
   ```bash
   python3 kalgara-vs-teach-5don-turns.py
   ```
   It reads every `.json` in the matchup folder, walks Kalgara's
   `don_at_start==5` turns, groups by action signature, and writes
   `kalgara-vs-teach-5don-turns.md` alongside.

## What the script does

- Filters to turns where the Kalgara player has 5 DON at turn start.
- Builds a short signature (`deploy:<id> · attach_don:<qty>->… · attack:LEADER · …`).
- Groups, counts wins/losses, also splits 1st-going vs 2nd-going.
- Tallies per-card play frequency + win rate for the turn.

## What's worth adapting

- The set of action verbs in `DROP_VERBS` — what counts as "bookkeeping" vs
  a real decision differs by leader.
- `tuple(sig[:5])` — first 5 tokens is enough for openings; bump higher for
  full-turn signatures.
- The 1st/2nd split — for second-going analysis, swap `don_at_start == 5`
  to `4` or `6` (see the DON-ramp gotcha in `../MANTRA.md`).
