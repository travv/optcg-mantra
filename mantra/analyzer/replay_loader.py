"""Load parsed Mantra replay JSONs."""
import glob
import json
import os
from typing import Iterator


def load_matchup_folder(folder: str) -> list[dict]:
    """Load every *.json under one matchup folder. Returns the parsed dicts.

    Skips files that fail to parse (truncated logs, partial writes).
    Each returned dict has `_metadata._local_path` populated for downstream
    reporting.
    """
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path) as f:
                p = json.load(f)
            p.setdefault("_metadata", {})["_local_path"] = path
            out.append(p)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def iter_matchup_folders(root: str) -> Iterator[tuple[str, str]]:
    """Yield (leader_id, opponent_id) for every matchup folder under `root`.

    Folder naming convention from `snapshot_replays`: `<leader>-vs-<opponent>`.
    """
    if not os.path.isdir(root):
        return
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if not os.path.isdir(full):
            continue
        if "-vs-" not in name:
            continue
        a, b = name.split("-vs-", 1)
        yield a, b


def leader_for_player(parsed: dict, player_name: str) -> str | None:
    info = parsed.get("players", {}).get(player_name)
    return info.get("leader") if info else None


def player_for_leader(parsed: dict, leader_id: str) -> str | None:
    for name, info in parsed.get("players", {}).items():
        if info.get("leader") == leader_id:
            return name
    return None
