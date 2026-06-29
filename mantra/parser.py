"""Parse an OPBounty combat log into structured turn-by-turn JSON.

Log shape (one line per event, plain text):

  Waiting for a Connection with Room ID:WD9BQRB
  PlayerA Has Connected
  Version is 1.37c
  [PlayerA] Leader is Kalgara [<mark><link="OP08-098">OP08-098</link></mark>]
  PlayerB Has Connected
  [PlayerB] Leader is Enel [<mark><link="OP15-058">OP15-058</link></mark>]
  [PlayerB] Chose to go First
  [PlayerA] Drew card from deck: Wyper [<mark><link="OP06-114">OP06-114</link></mark>]
  ...
  [PlayerA] End Turn
  ...
  [PlayerB] Concedes!
  [PlayerB] Loses

Cards are tagged inline either as the modern <mark><link="ID">name</link></mark>
form or a legacy ["ID">name] form. Player names always appear at the start of
their own action lines wrapped in `[]`; system lines (game start, version,
connections, in-flight combat resolution lines like "Attack Fails") are
prefix-free.

Design: substring routing + regex extraction, line by line. Unknown lines drop
into `unparsed_lines` rather than crashing — the game adds new effect strings
with every patch and we want a tolerant parser, not a brittle one.

DON tracking: maintain a running per-player counter. Each "Draw N Don" line
adds N; explicit "Activate N Don" lines also count as added; "Return Don" lines
subtract. Turn start is stamped as `don_at_start` on each turn object so
analyses can ask "what happened on the 5-DON turn?".
"""

import json
import re
import sys

_CARD_NEW = re.compile(r'<mark><link="([^"]+)">([^<]+)</link></mark>')
_CARD_OLD = re.compile(r'\["([^"]+)">([^\]]+)\]')


def _strip_cards(line: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (clean_line, [(card_id, card_name)]). Tags are replaced with the
    bare name so the remaining text is human-readable but tokenizable."""
    found: list[tuple[str, str]] = []

    def sub(m):
        found.append((m.group(1), m.group(2).strip()))
        return m.group(2).strip()

    line = _CARD_NEW.sub(sub, line)
    line = _CARD_OLD.sub(sub, line)
    return line, found


def _player_prefix(line: str) -> tuple[str | None, str]:
    """Extract the [Player#tag] prefix if present. Returns (player_or_none, rest)."""
    if not line.startswith("["):
        return None, line
    close = line.find("]")
    if close < 0:
        return None, line
    return line[1:close], line[close + 1 :].lstrip()


_RE_LEADER = re.compile(r"^Leader is\b")
_RE_DREW = re.compile(r"^Drew card from deck:")
_RE_HAND_PRE = re.compile(r"^Hand before Mulligan: \[(.*)\]")
_RE_HAND = re.compile(r"^Hand: \[(.*)\]")
_RE_TRASH = re.compile(r"^Trash: \[(.*)\]")
_RE_BOARD = re.compile(r"^Board: \[(.*)\]")
_RE_LIFE = re.compile(r"^Life:\s*(-?\d+)")
_RE_DRAW_DON = re.compile(r"^Draw (\d+) Don")
_RE_DRAW_CARD = re.compile(r"^Draw (\d+) Card")
_RE_ACTIVATE_DON = re.compile(r"^Activate (\d+) Don")
_RE_ATTACH_DON = re.compile(r"^Attach (\d+) Don to (.+?) \((\d+) Total\)")
_RE_RETURN_DON = re.compile(r"^Return (\d+) Don")
_RE_DEPLOY = re.compile(r"^Deploy (.+)$")
_RE_DISCARD_COUNTER = re.compile(r"^Discard (.+?) for Counter (\d+)")
_RE_ATTACKING = re.compile(r"^(.+?) attacking (.+)$")
_RE_BLOCKS = re.compile(r"^(.+?) Blocks$")
_RE_DESTROYED = re.compile(r"^(.+?) Destroyed$")
_RE_HIT = re.compile(r"^(.+?) hit for (\d+) damage")
_RE_END_TURN = re.compile(r"^End Turn$")
_RE_CHOSE_ORDER = re.compile(r"^Chose to go (First|Second)$")
_RE_CONCEDES = re.compile(r"^Concedes!$")
_RE_LOSES = re.compile(r"^Loses$")
_RE_WINS = re.compile(r"^Wins!$")

# System (no [player]) lines
_RE_ROOM = re.compile(r"^Waiting for a Connection with Room ID:\s*(.+)$")
_RE_VERSION = re.compile(r"^Version is (.+)$")
_RE_CONNECTED = re.compile(r"^(.+?) Has Connected$")
_RE_DISCONNECTED = re.compile(r"^Opponent Has Disconnected!$")
_RE_QUITS = re.compile(r"^Quits!$")
# Combat resolution mid-line, prefix-free: "Card [ID][8000] vs Card [ID][6000]"
_RE_COMBAT = re.compile(r"^(.+?)\[(\d+)\] vs (.+?)\[(\d+)\]\s*$")
_RE_ATTACK_FAILS = re.compile(r"^Attack Fails$")
# Newer-client packed state frames: "RZ1|<seq>|<player_idx>|<id>|<value>|..."
_RE_STATE_FRAME = re.compile(r"^RZ1\|")
# Leader-effect lines with no [player] prefix: "Enel [<mark>...]: Draw 1 Don"
_RE_LEADER_EFFECT = re.compile(r"^(.+?) \[<mark>")
# Effect-side don variants seen in real logs
_RE_DRAW_RESTED_DON = re.compile(r"^Draw (\d+) Rested Don$")
_RE_TRASH_FROM_LIFE = re.compile(r"^Trash (.+?) from Life$")
_RE_COST_RESTORED = re.compile(r"^(.+) cost restored$")


def _card_id(text: str, cards: list[tuple[str, str]]) -> str | None:
    """Cards stripped from a line are available in `cards`. If the text
    `Wyper` matches a stripped card's name, return its id. Used when the
    parser needs the ID of a referenced card by name."""
    for cid, cname in cards:
        if cname in text:
            return cid
    return None


def _parse_effect_subverb(text: str, cards: list[tuple[str, str]]) -> dict | None:
    """Detect a known sub-verb in a card-stripped effect line.

    The line shape is `Source [SRC_ID]: <verb> ...` (sometimes with target
    cards after). On match returns an action dict with a specific `verb`
    and the structured fields the verb implies. Returns None for shapes
    the parser doesn't recognise — the caller falls back to generic effect.

    `cards` is the in-order list of (id, name) tuples extracted from the
    original line; cards[0] is the source, cards[1:] are targets.
    """
    if ":" not in text:
        return None
    src = cards[0][0] if cards else None
    body = text.split(":", 1)[1].strip()
    targets = [cid for cid, _ in cards[1:]]
    first_target = targets[0] if targets else None

    if (m := re.match(r"^Attach (\d+) (Rested )?Don to\b", body)):
        return {"verb": "effect_attach_don", "source_card": src,
                "qty": int(m.group(1)), "rested": bool(m.group(2)),
                "to": first_target}
    if re.match(r"^Deploy\b", body):
        return {"verb": "effect_deploy", "source_card": src, "card": first_target}
    if re.match(r"^Takes Top Life\b", body):
        return {"verb": "effect_top_life", "source_card": src}
    if (m := re.match(r"^Send (\d+) Life to Hand\b", body)):
        return {"verb": "effect_send_life_to_hand", "source_card": src, "qty": int(m.group(1))}
    if (m := re.match(r"^Flip (\d+) Life Face Up\b", body)):
        return {"verb": "effect_flip_life", "source_card": src, "qty": int(m.group(1))}
    if (m := re.match(r"^Trash (\d+) Remaining Cards?\b", body)):
        return {"verb": "effect_trash_remaining", "source_card": src, "qty": int(m.group(1))}
    if re.match(r"^Trash\b", body):
        # Could be "Trash X from Life" (Teach) or "Trash X" (target trash).
        from_life = "from Life" in body
        return {"verb": "effect_trash_from_life" if from_life else "effect_trash",
                "source_card": src, "card": first_target}
    if (m := re.match(r"^Rest (\d+) Don\b", body)):
        return {"verb": "effect_rest_don", "source_card": src, "qty": int(m.group(1))}
    if re.match(r"^Rest\b", body):
        return {"verb": "effect_rest", "source_card": src, "card": first_target}
    if (m := re.match(r"^Buff .+? (-?\d+)\b", body)):
        return {"verb": "effect_buff", "source_card": src,
                "card": first_target, "amount": int(m.group(1))}
    if re.match(r"^Destroy\b", body):
        return {"verb": "effect_destroy", "source_card": src, "card": first_target}
    if (m := re.match(r"^Counter (\d+)\b", body)):
        return {"verb": "effect_counter", "source_card": src, "value": int(m.group(1))}
    if re.match(r"^Nullify effects( of)?\b", body):
        return {"verb": "effect_nullify", "source_card": src, "card": first_target}
    if re.match(r"^(?:<b>)?Reveal and Draw\b", body):
        return {"verb": "effect_reveal_draw", "source_card": src, "card": first_target}
    if (m := re.match(r"^Draw (\d+) Cards?\b", body)):
        return {"verb": "effect_draw_card", "source_card": src, "qty": int(m.group(1))}
    if (m := re.match(r"^Draw (\d+) Rested Don\b", body)):
        return {"verb": "draw_rested_don", "source_card": src, "qty": int(m.group(1))}
    if (m := re.match(r"^Draw (\d+) Don\b", body)):
        return {"verb": "draw_don", "source_card": src, "qty": int(m.group(1))}
    if re.match(r"^Activate Trigger\b", body):
        return {"verb": "effect_activate_trigger", "source_card": src}
    if re.match(r"^Activate Counter\b", body):
        return {"verb": "effect_activate_counter", "source_card": src}
    if re.match(r"^Can't Draw via Effects\b", body):
        return {"verb": "effect_block_draw", "source_card": src}
    if re.match(r"^Target of Attack changed\b", body):
        return {"verb": "effect_redirect_attack", "source_card": src}
    if re.match(r"^Add(?:ed)? card to (top|bottom)\b", body):
        m2 = re.match(r"^Add(?:ed)? card to (top|bottom)\b", body)
        return {"verb": "effect_topdeck", "source_card": src, "where": m2.group(1)}
    if (m := re.match(r"^Add .+? to (top|bottom) of Life\b", body)):
        return {"verb": "effect_add_to_life", "source_card": src,
                "card": first_target, "where": m.group(1)}
    if re.match(r"^Deployed\b", body) and "from Trash" in body:
        return {"verb": "effect_revive", "source_card": src, "card": first_target}
    if re.match(r"^Set\b", body):
        return {"verb": "effect_set", "source_card": src, "card": first_target}
    return None


def parse_log(raw: str) -> dict:
    out: dict = {
        "header": {"room_id": None, "version": None},
        "players": {},
        "first": None,
        "winner": None,
        "loser": None,
        "ended_by": None,  # "concede" | "life" | "disconnect" | None
        "pregame_actions": [],   # mulligan draws etc. before the first Draw N Don
        "turns": [],
        "unparsed_lines": [],
        "raw_line_count": 0,
    }

    don: dict[str, int] = {}
    turn_open: dict | None = None
    last_player_on_turn: str | None = None
    leader_to_player: dict[str, str] = {}  # card id -> player name

    def open_turn(player: str | None):
        nonlocal turn_open, last_player_on_turn
        turn_open = {
            "turn": len(out["turns"]) + 1,
            "player": player,
            "don_at_start": don.get(player, 0) if player else 0,
            "actions": [],
        }
        out["turns"].append(turn_open)
        last_player_on_turn = player

    def push(action: dict, raw: str):
        action["raw"] = raw
        if turn_open is None:
            # pregame (mulligan / pre-first-Draw-Don): file the action but
            # don't synthesize a turn boundary yet.
            out["pregame_actions"].append(action)
            return
        turn_open["actions"].append(action)

    for raw_line in raw.splitlines():
        out["raw_line_count"] += 1
        line = raw_line.rstrip()
        if not line:
            continue

        # System lines first
        if (m := _RE_ROOM.match(line)):
            out["header"]["room_id"] = m.group(1).strip()
            continue
        if (m := _RE_VERSION.match(line)):
            out["header"]["version"] = m.group(1).strip()
            continue
        if (m := _RE_CONNECTED.match(line)):
            name = m.group(1).strip()
            out["players"].setdefault(name, {"name": name, "leader": None})
            continue
        if _RE_DISCONNECTED.match(line):
            out["ended_by"] = "disconnect"
            continue
        if _RE_ATTACK_FAILS.match(line):
            push({"verb": "attack_fails"}, line)
            continue
        if _RE_STATE_FRAME.match(line):
            # Packed state-replication frames the newer client emits; useful
            # for the replay UI but not for action-level analysis. Count them
            # but don't crowd the action list — surface only as a counter.
            out.setdefault("state_frames", 0)
            out["state_frames"] += 1
            continue
        # Combat resolution lines come BEFORE leader-effect — both have the
        # "Card [<mark>...]" shape, but combat ends with "][POWER] vs ...".
        if (m := _RE_COMBAT.match(line)):
            atk_text, atk_pow, def_text, def_pow = m.groups()
            cleaned_atk, atk_cards = _strip_cards(atk_text)
            cleaned_def, def_cards = _strip_cards(def_text)
            push(
                {
                    "verb": "combat_resolve",
                    "attacker": atk_cards[0][0] if atk_cards else None,
                    "attacker_power": int(atk_pow),
                    "defender": def_cards[0][0] if def_cards else None,
                    "defender_power": int(def_pow),
                },
                line,
            )
            continue
        # Leader-effect lines (no [player] prefix): "Enel [<mark>...]: Draw 1 Don"
        # Require a colon to distinguish from combat lines.
        if not line.startswith("[") and "]:" in line and _RE_LEADER_EFFECT.match(line) and "[<mark>" in line:
            cleaned_full, cards = _strip_cards(line)
            src = cards[0][0] if cards else None
            controller = leader_to_player.get(src) if src else None
            sub = _parse_effect_subverb(cleaned_full, cards)
            if sub is not None:
                # draw_don/draw_rested_don add to the player's DON pool; only
                # this branch (no [player] prefix = leader speaking) can apply
                # the ramp since the player-prefixed Draw N Don line already
                # increments the counter elsewhere.
                if sub["verb"] in ("draw_don", "draw_rested_don") and controller:
                    don[controller] = don.get(controller, 0) + sub["qty"]
                    sub["don_total"] = don[controller]
                action = {"player": controller, "text": cleaned_full, **sub}
            else:
                action = {"verb": "effect", "player": controller,
                          "source_card": src, "text": cleaned_full}
            push(action, line)
            continue
        if (m := _RE_HIT.match(line)):
            cleaned, cards = _strip_cards(m.group(1))
            push(
                {
                    "verb": "hit_for",
                    "target": cards[0][0] if cards else None,
                    "damage": int(m.group(2)),
                },
                line,
            )
            continue

        # Player-prefixed lines
        player, rest = _player_prefix(line)
        if player is None:
            out["unparsed_lines"].append(line)
            continue

        cleaned, cards = _strip_cards(rest)

        if (m := _RE_LEADER.match(rest)):
            # Capture leader from the raw rest (has the <mark> tag) — cards[0] is the leader
            leader_id = cards[0][0] if cards else None
            out["players"].setdefault(player, {"name": player, "leader": None})
            out["players"][player]["leader"] = leader_id
            if leader_id:
                leader_to_player[leader_id] = player
            don.setdefault(player, 0)
            continue

        if (m := _RE_CHOSE_ORDER.match(cleaned)):
            order = m.group(1)
            out["first"] = player if order == "First" else _other_with_leader(out["players"], player)
            continue

        if _RE_DREW.match(cleaned):
            push(
                {
                    "verb": "draw_card",
                    "player": player,
                    "card": cards[0][0] if cards else None,
                },
                line,
            )
            continue

        if (m := _RE_HAND_PRE.match(cleaned)):
            push({"verb": "hand_pre_mulligan", "player": player, "cards": _split_ids(m.group(1))}, line)
            continue
        if (m := _RE_HAND.match(cleaned)):
            push({"verb": "hand_snapshot", "player": player, "cards": _split_ids(m.group(1))}, line)
            continue
        if (m := _RE_TRASH.match(cleaned)):
            push({"verb": "trash_snapshot", "player": player, "cards": _split_ids(m.group(1))}, line)
            continue
        if (m := _RE_BOARD.match(cleaned)):
            push({"verb": "board_snapshot", "player": player, "cards": _split_ids(m.group(1))}, line)
            continue
        if (m := _RE_LIFE.match(cleaned)):
            push({"verb": "life_snapshot", "player": player, "life": int(m.group(1))}, line)
            continue

        if (m := _RE_DRAW_DON.match(cleaned)):
            n = int(m.group(1))
            don[player] = don.get(player, 0) + n
            # First Draw-Don of a turn — if no open turn or it belongs to the
            # other player, open the new turn for this player. This is the
            # canonical turn-start signal in the log.
            if turn_open is None or turn_open.get("player") != player:
                open_turn(player)
            turn_open["don_at_start"] = don[player]
            push({"verb": "draw_don", "player": player, "qty": n, "don_total": don[player]}, line)
            continue
        if (m := _RE_DRAW_CARD.match(cleaned)):
            push({"verb": "draw_card_count", "player": player, "qty": int(m.group(1))}, line)
            continue
        if (m := _RE_ACTIVATE_DON.match(cleaned)):
            n = int(m.group(1))
            don[player] = don.get(player, 0) + n
            push({"verb": "activate_don", "player": player, "qty": n, "don_total": don[player]}, line)
            continue
        if (m := _RE_ATTACH_DON.match(cleaned)):
            n, target_text, total = int(m.group(1)), m.group(2), int(m.group(3))
            push(
                {
                    "verb": "attach_don",
                    "player": player,
                    "qty": n,
                    "to": _card_id(target_text, cards),
                    "to_total": total,
                },
                line,
            )
            continue
        if (m := _RE_RETURN_DON.match(cleaned)):
            n = int(m.group(1))
            don[player] = max(0, don.get(player, 0) - n)
            push({"verb": "return_don", "player": player, "qty": n, "don_total": don[player]}, line)
            continue

        if (m := _RE_DEPLOY.match(cleaned)):
            # The deployed card name is everything after "Deploy "; the id is in the inline tag.
            push(
                {
                    "verb": "deploy",
                    "player": player,
                    "card": cards[0][0] if cards else None,
                },
                line,
            )
            continue

        if (m := _RE_DISCARD_COUNTER.match(cleaned)):
            push(
                {
                    "verb": "counter",
                    "player": player,
                    "card": cards[0][0] if cards else None,
                    "value": int(m.group(2)),
                },
                line,
            )
            continue

        if (m := _RE_ATTACKING.match(cleaned)):
            atk_text, def_text = m.group(1).strip(), m.group(2).strip()
            attacker_id = cards[0][0] if cards else None
            defender_id = cards[1][0] if len(cards) > 1 else None
            # When the attack targets the leader itself, the defender's card-id is the leader.
            push(
                {
                    "verb": "attack",
                    "player": player,
                    "attacker": attacker_id,
                    "target": defender_id,
                    "target_is_leader": defender_id in leader_to_player if defender_id else False,
                },
                line,
            )
            continue

        if (m := _RE_BLOCKS.match(cleaned)):
            push({"verb": "block", "player": player, "blocker": cards[0][0] if cards else None}, line)
            continue
        if (m := _RE_DESTROYED.match(cleaned)):
            push({"verb": "destroyed", "by_player": player, "card": cards[0][0] if cards else None}, line)
            continue
        if _RE_END_TURN.match(cleaned):
            push({"verb": "end_turn", "player": player}, line)
            # Don't pre-open the next turn. The next "Draw N Don" line will
            # open it for the right player with the correct DON count.
            turn_open = None
            continue

        if _RE_CONCEDES.match(cleaned):
            out["ended_by"] = "concede"
            out["loser"] = player
            out["winner"] = _other_with_leader(out["players"], player)
            push({"verb": "concede", "player": player}, line)
            continue
        if _RE_LOSES.match(cleaned):
            out["loser"] = player
            out["winner"] = _other_with_leader(out["players"], player)
            continue
        if _RE_WINS.match(cleaned):
            out["winner"] = player
            out["loser"] = _other_with_leader(out["players"], player)
            continue
        if _RE_QUITS.match(cleaned):
            out["ended_by"] = "disconnect"
            out["loser"] = player
            out["winner"] = _other_with_leader(out["players"], player)
            push({"verb": "quit", "player": player}, line)
            continue

        # Effect lines like "Wyper [OP06-114]: Rest Jesus Burgess [OP09-086]"
        # — try the structured sub-verb extractor first, fall back to a
        # generic effect record so the action list always includes the line.
        sub = _parse_effect_subverb(cleaned, cards)
        if sub is not None:
            push({"player": player, "text": cleaned, **sub}, line)
        else:
            push(
                {
                    "verb": "effect",
                    "player": player,
                    "cards": [cid for cid, _ in cards],
                    "text": cleaned,
                },
                line,
            )

    return out


def _split_ids(s: str) -> list[str]:
    return [tok.strip() for tok in s.split(",") if tok.strip()]


def _other(players: dict, name: str) -> str | None:
    """Return any other player. Use _other_with_leader when correctness
    depends on picking the real opponent (the placeholder names "Your Client"
    / "Opponent" registered from "Has Connected" lines have no leader)."""
    for n in players:
        if n != name:
            return n
    return None


def _other_with_leader(players: dict, name: str) -> str | None:
    """Return the other player that has a `leader` assigned. Skips the
    leader-less placeholders ("Your Client", "Opponent") that the "Has
    Connected" system lines register, so that first-player / winner / loser
    attribution survives logs where the real nickname appears later."""
    for n, info in players.items():
        if n != name and info.get("leader"):
            return n
    # Fallback to plain _other so we don't break a log that lacks leader
    # info entirely (truncated header etc.).
    return _other(players, name)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: parser.py <path-to-log>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        raw = f.read()
    print(json.dumps(parse_log(raw), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
