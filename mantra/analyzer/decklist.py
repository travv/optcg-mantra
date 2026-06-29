"""Parse decklists from replay `_metadata`.

`_metadata.winner_deck` and `_metadata.loser_deck` are newline-delimited
strings. Each line is `<count>x<card_id>` (or just `<card_id>`). Line endings
may be CRLF.
"""
import re
from collections import Counter

_LINE_RE = re.compile(r"^\s*(?:(\d+)\s*[x*]\s*)?([A-Za-z0-9_]+-\d+)\s*$")


def parse_deck_string(s: str) -> Counter:
    """Return Counter mapping card_id -> count. Tolerates blank lines and CRLF."""
    out: Counter = Counter()
    if not s:
        return out
    for line in s.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        qty = int(m.group(1)) if m.group(1) else 1
        cid = m.group(2)
        out[cid] += qty
    return out


def decklist_from_replay(parsed: dict, side: str) -> Counter:
    """side ∈ {'winner', 'loser'}. Returns Counter of card_id -> count."""
    md = parsed.get("_metadata", {})
    raw = md.get(f"{side}_deck", "")
    return parse_deck_string(raw)


def leader_decklist_for(parsed: dict, leader_id: str) -> tuple[Counter, bool] | None:
    """Find the decklist for the side piloting `leader_id`. Returns
    (counter, won) or None if leader not in this replay.
    """
    md = parsed.get("_metadata", {})
    if md.get("winner_leader") == leader_id:
        return parse_deck_string(md.get("winner_deck", "")), True
    if md.get("loser_leader") == leader_id:
        return parse_deck_string(md.get("loser_deck", "")), False
    return None
