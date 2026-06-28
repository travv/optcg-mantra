#!/usr/bin/env python3
"""Mantra MCP server — exposes OPBounty replay metadata + combat logs.

Tools:
  - list_replays(...)        -> Replays collection rows (Firestore)
  - get_replay(path)         -> raw .log text from Firebase Storage
  - get_replay_parsed(path)  -> parsed JSON (see parser.py)
  - snapshot_replays(...)    -> bulk download to the vault

CLI:
  python3 server.py --selftest                  # verify Firebase auth + Firestore
  python3 server.py --probe <leader> [opponent] # quick CLI peek at recent replays
  python3 server.py                             # run as MCP server (stdio)
"""

import json
import os
import sys

from mcp.server.fastmcp import FastMCP

from auth import FirebaseAuth, AuthError
from firestore import Firestore, FirestoreError
from storage import Storage, StorageError
from parser import parse_log

mcp = FastMCP("mantra")
_auth = FirebaseAuth()
_fs = Firestore(_auth)
_store = Storage(_auth)

DEFAULT_VAULT_ROOT = os.path.expanduser(
    os.environ.get("MANTRA_VAULT_ROOT")
    or os.environ.get("OPBOUNTY_VAULT_ROOT")
    or "~/mantra-replays"
)


def _filter_replay(doc: dict, opponent: str | None, game_mode: str | None,
                   week: str | None, since: str | None, min_bounty: int | None,
                   _side: str) -> bool:
    """Apply client-side filters that Firestore can't always do composite."""
    if opponent is not None:
        # `_side` tells us which side WE filtered the leader on; opponent is the other side
        other = doc.get("loser_leader") if _side == "winner" else doc.get("winner_leader")
        if other != opponent:
            return False
    if game_mode is not None and str(doc.get("game_mode")) != str(game_mode):
        return False
    if week is not None and doc.get("week") != week:
        return False
    if since is not None and (doc.get("timestamp") or "") < since:
        return False
    if min_bounty is not None:
        wb = doc.get("winner_bounty") or 0
        lb = doc.get("loser_bounty") or 0
        if max(wb, lb) < min_bounty:
            return False
    return True


def _fetch_side(side: str, leader: str, limit: int) -> list[dict]:
    """Pull replays where leader is on the given side. Tries with order_by first;
    on Firestore composite-index errors, falls back to no-order + client-side sort."""
    where = [(f"{side}_leader", "EQUAL", leader)]
    # Firestore composite-index requirement is the most common failure here —
    # try the cheap path first, fall back gracefully.
    try:
        return _fs.run_query(
            "Replays",
            where=where,
            order_by=("timestamp", "DESCENDING"),
            limit=limit,
        )
    except FirestoreError as e:
        if "FAILED_PRECONDITION" in str(e) or "requires an index" in str(e):
            docs = _fs.run_query("Replays", where=where, limit=limit * 4)
            docs.sort(key=lambda d: d.get("timestamp") or "", reverse=True)
            return docs[:limit]
        raise


@mcp.tool()
def list_replays(
    leader: str | None = None,
    opponent: str | None = None,
    game_mode: str | None = None,
    week: str | None = None,
    since: str | None = None,
    min_bounty: int | None = None,
    limit: int = 50,
) -> dict:
    """List replay metadata from the OPBounty Firestore Replays collection.

    Args:
        leader: card id like "OP08-098" (Kalgara). Matches either side.
        opponent: card id; filters to games where the OTHER side is this leader.
        game_mode: queue/set code as a string (most are "0" = standard).
        week: ISO week like "2026-W25" to scope to one week.
        since: ISO-prefix timestamp; keep only replays >= this.
        min_bounty: keep replays where max(winner_bounty, loser_bounty) >= n.
        limit: cap on returned rows (post-merge). Default 50.

    Each row includes `path` (Firebase Storage path to the .log), `timestamp`,
    `winner_leader`, `loser_leader`, `winner_bounty`, `loser_bounty`,
    `game_mode`, `week`, and the two deck lists. The Replays collection is
    pre-filtered by the client to top-200 / 3000+ bounty uploaders.
    """
    try:
        if leader is None:
            # No leader filter: pull a raw page and apply client-side filters
            docs = _fs.run_query("Replays", order_by=("timestamp","DESCENDING"), limit=limit * 4)
            docs = [d for d in docs if _filter_replay(d, opponent, game_mode, week, since, min_bounty, "winner")]
            return {"count": len(docs[:limit]), "replays": docs[:limit]}

        # Two queries (winner_leader == X, loser_leader == X), merge by path.
        wins = _fetch_side("winner", leader, limit * 2)
        losses = _fetch_side("loser", leader, limit * 2)
        merged: dict[str, dict] = {}
        for d in wins:
            if _filter_replay(d, opponent, game_mode, week, since, min_bounty, "winner"):
                merged[d.get("path") or d.get("_name")] = d
        for d in losses:
            key = d.get("path") or d.get("_name")
            if key in merged:
                continue
            if _filter_replay(d, opponent, game_mode, week, since, min_bounty, "loser"):
                merged[key] = d
        rows = sorted(merged.values(), key=lambda d: d.get("timestamp") or "", reverse=True)
        return {"count": len(rows[:limit]), "replays": rows[:limit]}
    except (AuthError, FirestoreError) as e:
        return {"error": str(e)}


@mcp.tool()
def get_replay(path: str) -> dict:
    """Download a replay .log file by its storage path (the `path` field from
    list_replays). Returns the raw text body."""
    try:
        return {"path": path, "text": _store.download(path)}
    except (AuthError, StorageError) as e:
        return {"error": str(e), "path": path}


@mcp.tool()
def get_replay_parsed(path: str) -> dict:
    """Download a replay .log file and parse it into structured turn-by-turn JSON.
    See parser.parse_log for the shape."""
    try:
        raw = _store.download(path)
    except (AuthError, StorageError) as e:
        return {"error": str(e), "path": path}
    return {"path": path, **parse_log(raw)}


def _matchup_dir(a: str, b: str) -> str:
    """Canonical sorted-pair directory: Kalgara-vs-Teach always lives in one
    folder regardless of who won."""
    lo, hi = sorted([a, b])
    return f"{lo}-vs-{hi}"


def _safe_basename(timestamp: str | None, fallback_name: str) -> str:
    if timestamp:
        return timestamp.replace(":", "_")
    return fallback_name.replace("/", "__").replace(":", "_")


@mcp.tool()
def snapshot_replays(
    leader: str,
    opponent: str | None = None,
    game_mode: str | None = None,
    week: str | None = None,
    since: str | None = None,
    min_bounty: int | None = None,
    limit: int = 50,
    out_root: str | None = None,
) -> dict:
    """Bulk-download replays matching the filter; save raw .log + parsed .json
    to the vault.

    Files land at:
      <out_root>/<leaderA>-vs-<leaderB>/<timestamp>.{log,json}
    where (leaderA, leaderB) are the two leader ids in sorted order. The same
    file is skipped on re-runs.

    Defaults out_root to ~/Documents/travisobsidian/optcg-op16/replays/.
    """
    listing = list_replays(
        leader=leader, opponent=opponent, game_mode=game_mode, week=week,
        since=since, min_bounty=min_bounty, limit=limit,
    )
    if "error" in listing:
        return listing

    root = out_root or DEFAULT_VAULT_ROOT
    saved, skipped, failed = 0, 0, []
    paths_written: list[str] = []
    for doc in listing["replays"]:
        path = doc.get("path")
        if not path:
            continue
        a, b = doc.get("winner_leader"), doc.get("loser_leader")
        if not (a and b):
            continue
        folder = os.path.join(root, _matchup_dir(a, b))
        os.makedirs(folder, exist_ok=True)
        base = _safe_basename(doc.get("timestamp"), os.path.basename(path))
        log_path = os.path.join(folder, f"{base}.log")
        json_path = os.path.join(folder, f"{base}.json")

        if os.path.exists(log_path) and os.path.exists(json_path):
            skipped += 1
            continue
        try:
            raw = _store.download(path)
        except StorageError as e:
            failed.append({"path": path, "error": str(e)})
            continue
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(raw)
        parsed = parse_log(raw)
        # Fold the metadata in so analysis scripts have everything in one file.
        parsed["_metadata"] = {
            k: doc.get(k) for k in (
                "path", "timestamp", "week", "game_mode",
                "winner_leader", "loser_leader",
                "winner_bounty", "loser_bounty",
                "winner_deck", "loser_deck",
            )
        }
        # If the log was truncated and we couldn't infer a winner, trust the
        # metadata's winner_leader.
        if parsed.get("winner") is None:
            for name, info in parsed.get("players", {}).items():
                if info.get("leader") == doc.get("winner_leader"):
                    parsed["winner"] = name
                    parsed["loser"] = next((n for n in parsed["players"] if n != name), None)
                    parsed["ended_by"] = parsed.get("ended_by") or "log_truncated"
                    break
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        paths_written.append(log_path)
        saved += 1
    return {
        "saved": saved,
        "skipped": skipped,
        "failed_count": len(failed),
        "failures": failed[:5],
        "out_root": root,
        "matchup_dirs": sorted({os.path.dirname(p) for p in paths_written}),
    }


def _cli() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        try:
            res = _auth.selftest()
            docs = _fs.run_query("Replays", limit=1)
            res["firestore_sample"] = {
                "count": len(docs),
                "first_path": docs[0].get("path") if docs else None,
            }
            print(json.dumps(res, indent=2))
            return 0
        except (AuthError, FirestoreError) as e:
            print(f"SELFTEST FAILED: {e}", file=sys.stderr)
            return 1
    if args and args[0] == "--probe":
        leader = args[1] if len(args) > 1 else "OP08-098"
        opponent = args[2] if len(args) > 2 else None
        res = list_replays(leader=leader, opponent=opponent, limit=5)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
