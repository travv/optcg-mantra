"""Locate matchup folders under `$MANTRA_VAULT_ROOT`."""
import os


def vault_root() -> str:
    """Resolve the replay vault root from env, with the historical
    `OPBOUNTY_VAULT_ROOT` fallback. Raises if neither is set."""
    p = os.environ.get("MANTRA_VAULT_ROOT") or os.environ.get("OPBOUNTY_VAULT_ROOT")
    if not p:
        raise RuntimeError(
            "MANTRA_VAULT_ROOT not set. Point it at the directory where "
            "`snapshot_replays` caches matchup folders."
        )
    return os.path.expanduser(p)


def matchup_folder_path(my_leader: str, opp_leader: str, root: str | None = None) -> str:
    """Return the canonical folder path. May not exist on disk yet."""
    root = root or vault_root()
    return os.path.join(root, f"{my_leader}-vs-{opp_leader}")


def has_matchup(my_leader: str, opp_leader: str, root: str | None = None) -> bool:
    return os.path.isdir(matchup_folder_path(my_leader, opp_leader, root))


def matchup_folder_either_order(a: str, b: str, root: str | None = None) -> str | None:
    """`snapshot_replays` writes one folder per pair in the directionality it
    was queried. Return whichever folder exists.
    """
    p1 = matchup_folder_path(a, b, root)
    p2 = matchup_folder_path(b, a, root)
    if os.path.isdir(p1):
        return p1
    if os.path.isdir(p2):
        return p2
    return None
