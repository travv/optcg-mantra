# Mantra — install guide

Local MCP server that pulls OPBounty (OPTCG simulator) combat-log replays from
the game's Firebase backend, plus a parser that turns the raw `.log` text into
turn-by-turn structured JSON. The tool is called **Mantra**; the data source
is **OPBounty**.

OPBounty's Replays collection is pre-filtered server-side to top-200 ladder /
≥3000-bounty pilots, so every replay you pull is high-skill play. That's the
killer feature — see `MANTRA.md` for what's in the data and how to think
about it.

## 1. Pick a home for the code

Clone the repo (or unpack the bundle) somewhere convenient — e.g.
`~/Documents/optcg-mantra`. The MCP server code lives in the `mantra/`
subfolder.

## 2. Install Python deps

Python 3.10+ recommended.

```bash
pip3 install --user mcp httpx certifi
```

## 3. Pick a vault root (where snapshots get cached)

The server caches downloaded replays (`.log` + parsed `.json`) under a vault
root you control. Set `OPBOUNTY_VAULT_ROOT` to wherever you want them to land
— most people point this at an Obsidian vault folder so the JSON ends up
searchable alongside their notes.

```bash
# Add to ~/.zshrc or ~/.bashrc:
export OPBOUNTY_VAULT_ROOT="$HOME/Documents/myvault/optcg/replays"
```

If unset, the server defaults to `~/opbounty-replays/`.

## 4. Verify auth + Firestore work

```bash
cd ~/Documents/optcg-mantra/mantra
python3 server.py --selftest
```

Expect:
```json
{
  "signin": "ok",
  "id_token_prefix": "eyJhbGciOi...",
  "expires_in_s": 3300,
  "project_id": "opbounty-3623c",
  "firestore_sample": {"count": 1, "first_path": "Replays/2026-W..."}
}
```

You can also do a quick CLI peek without going through Claude:
```bash
python3 server.py --probe OP08-098            # Kalgara replays
python3 server.py --probe OP08-098 OP16-080   # Kalgara vs Teach
```

## 5. Register with Claude Code

Edit `~/.claude.json` (user scope — available in every project) and add an
entry under `mcpServers`:

```json
{
  "mcpServers": {
    "mantra": {
      "type": "stdio",
      "command": "python3",
      "args": ["/Users/YOU/Documents/optcg-mantra/mantra/server.py"],
      "env": {
        "OPBOUNTY_VAULT_ROOT": "/Users/YOU/Documents/myvault/optcg/replays"
      }
    }
  }
}
```

Restart Claude Code (or `/mcp` and reconnect). The four tools should appear:
- `list_replays`
- `get_replay`
- `get_replay_parsed`
- `snapshot_replays`

## 6. Teach your Claude the domain

Read `MANTRA.md` next to this file — it's a short brief written for Claude.
Either copy it into your `~/.claude/CLAUDE.md` (user-global) or your
project-level `CLAUDE.md` so Claude understands what OPBounty is, what's in
the Replays collection, the DON-ramp 1st/2nd gotcha, and the cached vault
layout before you ask it to do analysis.

## 7. Try the example

`example-analysis/` contains a worked Kalgara-vs-Teach 5-DON turn analysis —
the snapshot pull, the Python that groups action signatures, and the
markdown report. It's the best template for "I want to see what high-MMR
pilots do in matchup X." Copy it, swap leader ids, run.

## A note on credentials

The Firebase email/password baked into `auth.py` are not secrets — every
OPBounty install signs in with the same shared service account, and the
in-app opt-in explicitly says replays are shared for public reports. No
account of yours is involved.
