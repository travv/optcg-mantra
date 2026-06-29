# Mantra — OPTCG top-ladder replay analyzer

Observation haki for OPTCG ladder play. Named after _mantra_, One Piece's word
for the ability to sense an opponent's intentions before they act — which is
exactly what reading top-ladder replays gives you.

The upstream data source is **OPBounty** (an OPTCG simulator). OPBounty's
`Replays` Firestore collection is pre-filtered server-side to top-200 ladder /
≥3000-bounty pilots, so every replay you pull is high-skill play. Mantra is an
MCP server + parser + Claude-facing brief that lets you list, snapshot, and
analyze those replays from Claude Code.

## Read in this order

1. **`INSTALL.md`** — get the MCP server running, register it with Claude
   Code, set `MANTRA_VAULT_ROOT`, verify with `--selftest`.
2. **`MANTRA.md`** — the Claude-facing brief. Copy into your
   `~/.claude/CLAUDE.md` or project `CLAUDE.md` so Claude understands the
   domain (Replays schema, DON-ramp 1st/2nd gotcha, vault layout) before you
   ask it to do analysis.
3. **`example-analysis/`** — a small family of worked analyses. Start with
   `kalgara-vs-teach-5don-turns.py` (turn-N decision study), then look at
   `g1-loss-replay-matcher.py` (personal log → matched replays),
   `c2-tech-adoption-trend.py` (per-leader weekly decklist movement), and
   `b2-pivotal-turn-detector.py` (where did this loss start losing?). The
   later three share a small kernel in `mantra/analyzer/`.

## Layout

```
optcg-mantra/
├── README.md                this file
├── INSTALL.md               setup + Claude registration
├── MANTRA.md                brief for Claude (drop into CLAUDE.md)
├── mantra/
│   ├── auth.py              Firebase signIn → 1h ID token
│   ├── firestore.py         tiny structuredQuery client
│   ├── storage.py           .log file downloader
│   ├── parser.py            combat log → turn/action JSON
│   ├── server.py            FastMCP entry (4 tools + --selftest / --probe)
│   ├── analyzer/            reusable kernel for example-analysis scripts
│   │   ├── replay_loader.py   load parsed JSONs from a matchup folder
│   │   ├── decklist.py        parse winner_deck / loser_deck strings
│   │   ├── matchup_lookup.py  locate matchup folders under MANTRA_VAULT_ROOT
│   │   ├── action_token.py    action -> token + main/existing-board split
│   │   ├── assets.py          card-art download + cache
│   │   └── render.py          vault HTML thumbnails / repo plain-text
│   └── README.md            tool-surface reference
└── example-analysis/
    ├── README.md            how to reproduce + how to adapt
    ├── kalgara-vs-teach-5don-turns.py   self-contained worked example
    ├── kalgara-vs-teach-5don-turns.md
    ├── g1-loss-replay-matcher.py        game log -> matched winning replays
    ├── c2-tech-adoption-trend.py        per-leader weekly decklist movement
    └── b2-pivotal-turn-detector.py      single-replay WP-collapse analysis
```

"OPBounty" refers to the upstream game/data source throughout — only the tool
itself is "Mantra."
