# Mantra

Local MCP server that pulls OPBounty (OPTCG simulator) combat-log replays from
the developer's Firebase backend (`opbounty-3623c`). Registered with Claude
Code at user scope as `mantra`.

## Surface

| Tool | Returns |
|---|---|
| `list_replays(leader=, opponent=, game_mode=, week=, since=, min_bounty=, limit=)` | Replays metadata rows (winner/loser leaders, bounties, deck lists, storage path). |
| `get_replay(path)` | Raw `.log` text from Firebase Storage. |
| `get_replay_parsed(path)` | Parsed JSON (see `parser.py` — turns, actions, DON tracking, winner). |
| `snapshot_replays(leader, opponent=, game_mode=, ..., limit=, out_root=)` | Bulk-pull to the vault at `<root>/<leaderA>-vs-<leaderB>/<timestamp>.{log,json}`, canonical sorted-pair folders. |

CLI:
- `python3 server.py --selftest` → confirm Firebase auth + a Firestore read.
- `python3 server.py --probe <leader> [opponent]` → quick peek at recent replays.

## How auth works (and a security note)

OPBounty embeds Firebase config + a shared service-account email/password
directly in its Godot `.pck` bundle. Every OPBounty install signs in as the
same user:

- API key: `AIzaSyC9qxZxJZbt2NJkjSyU9b3KJUfRHVFPuVs` (public by design)
- Email: `opbountyclient@opbounty.com`
- Password: `ClientUser`

These are NOT secrets — they ship to every user. We use the same Firebase REST
API the app uses: POST `signInWithPassword` → get a 1-hour ID token → send as
`Authorization: Bearer …` on every Firestore / Storage call. No on-disk
credential file; everything is in `auth.py`.

The OPBounty in-app opt-in says explicitly: *"by playing using OPBounty you
agree to share your personal matches data to improve the server stats and
public reports."* Replays are public-by-policy. Only top-200-ladder or
≥3000-bounty pilots upload, so the Replays collection is pre-filtered to
high-skill play.

## Data shapes

**`Replays` Firestore doc:**
```
path:            "Replays/2026-W25/0/OP08-098/OP16-080_2527_1702.log"
timestamp:       "2026-06-22T11:55:26"  (ISO local)
week:            "2026-W25"
game_mode:       "0"  # standard queue; "1"/"2" are minor queues
winner_leader:   "OP08-098"             # raw card id
loser_leader:    "OP16-080"
winner_bounty:   2527.9                  # MMR
loser_bounty:    1702.5
winner_deck:     "1xOP08-098\n4xOP15-108\n..."   # newline string, sometimes ""
loser_deck:      "..."
```

**`.log` storage payload:** plain text, line-per-event. See `parser.py` for
the full vocabulary. Card ids tagged inline as
`<mark><link="OP15-114">5c Wyper</link></mark>`.

## Vault paths

- Cached replays: `$OPBOUNTY_VAULT_ROOT/<leaderA>-vs-<leaderB>/` (default
  `~/opbounty-replays/`). Set the env var in your MCP registration to point
  at an Obsidian vault folder or wherever you want snapshots cached.

## Notes

- Firestore composite-index errors on `(leader == X) AND order_by(timestamp)`:
  caught and silently retried as filter-only + client-side sort.
- Truncated logs (no `Concedes!` / `Wins!` line): the snapshot tool falls back
  to the metadata's `winner_leader` to attribute the winner, marking
  `ended_by = "log_truncated"`.
- Parser tolerates unknown lines via `unparsed_lines` rather than crashing —
  the game's log strings change between patches.
- Newer client (>= 1.40) emits packed `RZ1|…` state-replication frames
  interleaved with human-readable events. We count them as `state_frames` and
  skip them for action analysis.
