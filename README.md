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
   Code, set `OPBOUNTY_VAULT_ROOT`, verify with `--selftest`.
2. **`MANTRA.md`** — the Claude-facing brief. Copy into your
   `~/.claude/CLAUDE.md` or project `CLAUDE.md` so Claude understands the
   domain (Replays schema, DON-ramp 1st/2nd gotcha, vault layout) before you
   ask it to do analysis.
3. **`example-analysis/`** — Kalgara-vs-Teach 5-DON turn analysis as a
   template. Snapshot → parse from cache → group action signatures → report.

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
│   └── README.md            tool-surface reference
└── example-analysis/
    ├── README.md            how to reproduce + how to adapt
    ├── kalgara-vs-teach-5don-turns.py
    └── kalgara-vs-teach-5don-turns.md
```

"OPBounty" refers to the upstream game/data source throughout — only the tool
itself is "Mantra."
