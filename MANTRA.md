# Mantra — what it is, how to use it

This brief is written for Claude. Drop it into your global or project
`CLAUDE.md` so Claude understands the domain before being asked to do analysis.

**Mantra** is the name of this tool — after _mantra_, One Piece's word for
observation haki (the ability to sense an opponent's intentions before they
act). That's the analogy: reading top-ladder replays lets you see what good
pilots are about to do on turn N. The upstream data source is **OPBounty**
(an OPTCG simulator); Mantra is just the MCP server + parser that exposes it.

## What OPBounty is

OPBounty is a desktop OPTCG (One Piece Card Game) simulator built in Godot 4.
The app uploads every match's combat log to a Firebase backend (project
`opbounty-3623c`). The Mantra MCP server in this folder exposes that
collection so Claude can list, fetch, and parse replays.

This is a different source from `stats.tcgmatchmaking.com` / `cardkaizoku.com`,
which only publish aggregate stats — OPBounty has the per-game combat logs.

## The killer feature: top-MMR pre-filter

OPBounty only uploads replays from pilots who are either top-200 on the ladder
OR sitting at ≥3000 bounty (MMR). The entire `Replays` collection is therefore
pre-filtered to high-skill play. When analyzing matchups, treat the sample as
"what good pilots do," not "what the average ladder does."

## Tools

| Tool | Purpose |
|---|---|
| `list_replays(leader=, opponent=, game_mode=, week=, since=, min_bounty=, limit=)` | Firestore metadata rows. Leader matches either side. Auto-merges winner/loser sides. |
| `get_replay(path)` | Raw `.log` text from Firebase Storage. |
| `get_replay_parsed(path)` | Parsed JSON — turns, actions, DON tracking, winner. |
| `snapshot_replays(leader, ...)` | Bulk-pull to `MANTRA_VAULT_ROOT`. Saves `.log` + `.json`. Idempotent — re-runs skip already-cached files. |

Leaders are referenced by **raw card id** (e.g. `OP08-098` for Kalgara,
`OP16-080` for Teach), NOT by normalized names like `"MonkeyDLuffy"`. The
file-path uses normalized names but the document fields use raw codes.

## Replay metadata shape

```
path:            "Replays/2026-W25/0/OP08-098/OP16-080_2527_1702.log"
timestamp:       "2026-06-22T11:55:26"   # ISO local
week:            "2026-W25"
game_mode:       "0"                      # standard queue, >99% of uploads.
                                         # "1"/"2" are minor queues (small samples).
                                         # Not a set code — don't pass "OP16" here.
winner_leader:   "OP08-098"
loser_leader:    "OP16-080"
winner_bounty:   2527.9                   # MMR
loser_bounty:    1702.5
winner_deck:     "1xOP08-098\n4xOP15-108\n..."   # newline string, sometimes ""
loser_deck:      "..."
```

## Combat log format

Plain text, line-per-event. Card ids tagged inline as
`<mark><link="OP15-114">5c Wyper</link></mark>`. Player lines prefixed with
`[Discord#1234]`. Leader-effect lines (no player prefix) start with the
leader's character name.

Newer client (≥1.40) interleaves `RZ1|…` packed state-replication frames —
the parser counts them as `state_frames` and skips them. Logs that end without
an explicit `Wins!` / `Concedes!` line fall back to the metadata's
`winner_leader` and get marked `ended_by="log_truncated"`.

## DON-ramp gotcha — critical for any turn-N analysis

OPTCG ramps DON statically: +2 per turn, capped at 10.

- Going **1st**: DON sequence is `1, 3, 5, 7, 9` (capped).
- Going **2nd**: DON sequence is `2, 4, 6, 8, 10`.

This means a query like "what does this leader do on the 5-DON turn?" *only
matches first-going games* — second-going games skip from 4 to 6 DON and
never have a 5-DON turn. The parser stamps `don_at_start` on each turn from
the in-game `Draw N Don` line; filter on that, not on turn number.

## Vault layout (where `snapshot_replays` writes)

Set `MANTRA_VAULT_ROOT` to wherever cached replays should live (default
`~/mantra-replays/`; the legacy `OPBOUNTY_VAULT_ROOT` is honored as a
fallback).

```
<MANTRA_VAULT_ROOT>/
  <leaderA>-vs-<leaderB>/         # leader codes in SORTED order
    <timestamp>.log               # raw combat log
    <timestamp>.json              # parsed + _metadata (deck, bounties, etc.)
```

Sorted-pair folder means Kalgara-vs-Teach lives in ONE folder
(`OP08-098-vs-OP16-080`) regardless of who won — don't expect winner-first.

## Parsed JSON shape (per replay)

```
{
  "players": {"[Discord#1234]": {"leader": "OP08-098", "going": "first"}, ...},
  "turns": [
    {
      "turn": 1, "player": "[Discord#1234]", "don_at_start": 1,
      "actions": [
        {"kind": "draw", ...},
        {"kind": "deploy", "card": "OP15-114", ...},
        {"kind": "attach_don", "qty": 1, "target": "OP08-098"},
        {"kind": "attack", "target": "LEADER"},
        {"kind": "counter", "card": "OP09-086", "value": 1000},
        {"kind": "effect", "source_card": "OP08-098", ...},
        ...
      ]
    },
    ...
  ],
  "winner": "[Discord#1234]",
  "loser":  "[Discord#5678]",
  "ended_by": "leader_loses" | "concede" | "log_truncated",
  "state_frames": 412,
  "_metadata": { ... mirror of the Firestore doc ... }
}
```

## How to do a matchup analysis (the standard recipe)

1. **Pull the sample.** Call `snapshot_replays(leader=<A>, opponent=<B>,
   game_mode="0", limit=300)`. The folder will populate at
   `<vault>/<A>-vs-<B>/`.
2. **Walk the cached `.json` files.** Don't re-fetch — parse from disk. The
   `_metadata` field carries the deck lists and bounties.
3. **Pick the turn(s) you care about.** Filter turns by `player` (the leader
   you're studying), `don_at_start`, or turn index. Be aware of the 1st/2nd
   DON-ramp split.
4. **Build action signatures.** Concatenate the first N meaningful actions
   (`deploy:<id>`, `attach_don:<qty>-><target>`, `attack:LEADER|BODY`,
   `counter:<id>(<value>)`, `effect:<source_card>`). Skip snapshot lines and
   combat-resolve bookkeeping.
5. **Group by signature, count wins/losses.** Look for high-frequency openings
   with above- or below-average win rates.

See `example-analysis/` for a working version of this against the
Kalgara-vs-Teach 5-DON turn.

## Things to remember

- **`game_mode` is a queue code, not a set code.** Default to `"0"`.
- **Leader fields are raw card ids.** No normalized names.
- **Top-MMR sample only.** Don't generalize claims to ladder average.
- **Truncated logs exist.** `ended_by="log_truncated"` games count the
  metadata winner but have incomplete action sequences — drop them if you
  need full-game data.
- **`don_at_start == 5` can fire more than once** in matchups with
  return-DON effects. For most decks it fires once per game; if not, filter
  to first-occurrence-per-replay.
- **Cookie/credential is shared and public.** No per-user auth.
