#!/usr/bin/env python3
"""G1 — personal game-log losses → matched top-MMR winning replays.

Parses a personal game-log markdown table (default schema: the table written
by `optcg_logger.py` — Date | Time | My Deck | Opponent | Result | Roll |
Order | Tags | Notes) and, for each LOSS row, finds up to 3 top-MMR winning
replays of the same `(my_leader, opponent_leader, going_1st/2nd)` from the
OPBounty corpus snapshotted into `$MANTRA_VAULT_ROOT`.

Matching granularity: leader pair + turn order only. Rows with an
unparseable opponent (no `(OPxx-yyy)` token) are reported but not matched.
Missing matchups emit a `snapshot_replays(...)` hint so you can populate the
corpus on demand.

Outputs a sidecar markdown file alongside the input game log (default name:
`<input>-study.md`). The input game log is never modified — the logger owns
that file.

Usage:
    MANTRA_VAULT_ROOT=~/vault/replays \\
        python3 g1-loss-replay-matcher.py \\
            --games-md ~/vault/data/game-logs/games.md \\
            --out      ~/vault/data/game-logs/games-study.md
"""
import argparse
import os
import re
import sys
from collections import defaultdict

# Allow running directly: add repo root to sys.path so `mantra.analyzer` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mantra.analyzer.matchup_lookup import matchup_folder_either_order, vault_root
from mantra.analyzer.replay_loader import load_matchup_folder, player_for_leader

MAX_MATCHES_PER_LOSS = 3
CARD_ID_RE = re.compile(r"\(([A-Za-z0-9]+-\d+)\)")


def parse_games_md(path: str) -> list[dict]:
    """Return one dict per data row of a pipe-table game log.

    Expected columns (positions): Date, Time, My Deck, Opponent, Result, Roll,
    Order, Tags, Notes. Tolerates the header + separator + intro lines that
    obsidian-style markdown tables typically have.
    """
    rows = []
    with open(path) as f:
        for line in f:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.rstrip("\n").split("|")[1:-1]]
            if not cells or cells[0] in ("Date",) or cells[0].startswith("---"):
                continue
            if len(cells) < 8:
                continue
            rows.append({
                "date": cells[0],
                "time": cells[1],
                "my_deck": cells[2],
                "opponent": cells[3],
                "result": cells[4],
                "roll": cells[5],
                "order": cells[6],
                "tags": cells[7] if len(cells) > 7 else "",
                "notes": cells[8] if len(cells) > 8 else "",
            })
    return rows


def extract_card_id(cell: str) -> str | None:
    m = CARD_ID_RE.search(cell)
    return m.group(1) if m else None


def find_winning_replays(
    my_leader: str,
    opp_leader: str,
    going_1st: bool,
    root: str,
    max_n: int = MAX_MATCHES_PER_LOSS,
) -> tuple[list[dict], str | None]:
    folder = matchup_folder_either_order(my_leader, opp_leader, root=root)
    if not folder:
        return [], None
    parsed = load_matchup_folder(folder)

    matches = []
    for p in parsed:
        my_player = player_for_leader(p, my_leader)
        if not my_player:
            continue
        if p.get("winner") != my_player:
            continue
        first_player = p.get("first")
        my_first = first_player == my_player
        if my_first != going_1st:
            continue
        md = p.get("_metadata", {})
        matches.append({
            "path": md.get("_local_path") or md.get("path", "?"),
            "timestamp": md.get("timestamp", ""),
            "bounty": md.get(
                "winner_bounty" if p.get("winner") == my_player else "loser_bounty",
                "",
            ),
        })

    matches.sort(key=lambda m: m["timestamp"], reverse=True)
    return matches[:max_n], folder


def obsidian_link(local_path: str, vault_link_root: str | None) -> str:
    """Render a vault-relative obsidian [[wikilink]] when `vault_link_root` is
    a prefix of `local_path`. Otherwise fall back to a backticked absolute
    path."""
    if vault_link_root:
        vault_link_root = os.path.expanduser(vault_link_root)
        if local_path.startswith(vault_link_root):
            rel = local_path[len(vault_link_root):].lstrip("/")
            rel = rel.rsplit(".", 1)[0]
            return f"[[{rel}]]"
    return f"`{local_path}`"


def build_sidecar(rows: list[dict], root: str, vault_link_root: str | None) -> str:
    L: list[str] = []
    L.append("---")
    L.append("title: \"Game-log study links\"")
    L.append("tags:")
    L.append("  - optcg")
    L.append("  - game-log")
    L.append("  - auto-generated")
    L.append("---")
    L.append("")
    L.append("# Game-log study links")
    L.append("")
    L.append("For each LOSS row in the linked game log, surfaces up to "
             f"{MAX_MATCHES_PER_LOSS} top-MMR winning replays of the same "
             "`(my_leader, opponent_leader, going_1st/2nd)` from the OPBounty "
             "corpus. Re-run the script after appending to the game log or "
             "snapshotting new matchups.")
    L.append("")

    losses = [r for r in rows if r["result"] == "L"]
    L.append(f"**Losses indexed:** {len(losses)} (of {len(rows)} total rows)")
    L.append("")

    missing_matchups: dict[tuple[str, str], int] = defaultdict(int)
    unparseable: list[dict] = []
    matched_count = 0

    L.append("## Losses")
    L.append("")
    L.append("| Date | My deck | Opponent | Order | Study |")
    L.append("|---|---|---|---|---|")

    for row in losses:
        my_id = extract_card_id(row["my_deck"])
        opp_id = extract_card_id(row["opponent"])
        going_1st = row["order"].startswith("1")

        if not my_id:
            study = "🤷 unparseable my-deck"
        elif not opp_id:
            study = "🤷 unparseable opponent"
            unparseable.append(row)
        else:
            matches, folder = find_winning_replays(my_id, opp_id, going_1st, root)
            if folder is None:
                study = (
                    f"📭 no corpus yet — run `snapshot_replays(leader='{my_id}', "
                    f"opponent='{opp_id}')` in the mantra MCP"
                )
                missing_matchups[(my_id, opp_id)] += 1
            elif not matches:
                study = (
                    f"⚠️ corpus has no `{my_id}` win going {row['order']} vs `{opp_id}`"
                )
            else:
                links = " · ".join(obsidian_link(m["path"], vault_link_root) for m in matches)
                study = links
                matched_count += 1

        opp_display = row["opponent"].replace("|", "\\|")
        my_display = row["my_deck"].replace("|", "\\|")
        L.append(
            f"| {row['date']} | {my_display} | {opp_display} | "
            f"{row['order']} | {study} |"
        )

    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(f"- **Matched:** {matched_count} loss rows linked to ≥1 winning top-MMR replay.")
    L.append(f"- **Unparseable opponent:** {len(unparseable)} rows.")
    L.append(f"- **Matchups not yet snapshotted:** {len(missing_matchups)} unique pairs.")
    if missing_matchups:
        L.append("")
        L.append("### Suggested snapshots")
        L.append("")
        L.append("Run via the mantra MCP `snapshot_replays` tool to populate the corpus:")
        L.append("")
        for (my_id, opp_id), n in sorted(
            missing_matchups.items(), key=lambda kv: -kv[1]
        ):
            L.append(
                f"- `snapshot_replays(leader='{my_id}', opponent='{opp_id}')` "
                f"— **{n}** loss row{'s' if n != 1 else ''}"
            )

    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games-md", required=True,
                    help="Path to the game-log markdown file.")
    ap.add_argument("--out", required=True,
                    help="Output sidecar path. Will be overwritten.")
    ap.add_argument("--vault-link-root", default=None,
                    help="If set, replay paths under this prefix are rendered "
                         "as obsidian [[wikilinks]] relative to the prefix.")
    args = ap.parse_args()

    root = vault_root()
    games_path = os.path.expanduser(args.games_md)
    if not os.path.exists(games_path):
        print(f"Game log not found: {games_path}", file=sys.stderr)
        sys.exit(1)
    rows = parse_games_md(games_path)
    print(f"Parsed {len(rows)} rows from {games_path}")
    sidecar = build_sidecar(rows, root, args.vault_link_root)
    out_path = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(sidecar)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
