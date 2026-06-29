"""Canonical action -> compact-string serializer.

Matches the kalgara-vs-teach-5don-turns.py inline version verbatim so the
regression check passes (existing report must reproduce byte-identically when
ported to the library).
"""

# Verbs that are pure bookkeeping / informational and should be dropped before
# building action signatures. Callers can extend per-analysis.
DEFAULT_DROP_VERBS = {
    "hand_snapshot", "trash_snapshot", "board_snapshot", "life_snapshot",
    "draw_card_count", "combat_resolve", "hit_for", "attack_fails",
    "draw_don", "block", "destroyed", "draw_card", "hand_pre_mulligan",
    "draw_rested_don",
    "effect_reveal_draw",
    "effect_block_draw",
    "effect_activate_trigger",
    "effect_activate_counter",
    "effect_redirect_attack",
    "effect_topdeck", "effect_set", "effect_flip_life",
    "effect_buff", "effect_nullify", "effect_destroy", "effect_counter",
    "effect_trash", "effect_trash_from_life", "effect_trash_remaining",
    "effect_rest", "effect_rest_don",
}

# Verbs that represent the turn-player's main play (vs. existing-board swings).
MAIN_PLAY_VERBS = {
    "deploy", "effect_deploy", "attach_don", "effect_attach_don",
    "counter", "effect_top_life", "effect_send_life_to_hand",
    "effect_draw_card", "effect_revive", "effect_add_to_life",
}


def action_token(a: dict, drop_verbs: set[str] | None = None) -> str | None:
    """Serialize one action dict to a compact token, or None to drop it."""
    if drop_verbs is None:
        drop_verbs = DEFAULT_DROP_VERBS
    v = a.get("verb")
    if v in drop_verbs:
        return None
    if v == "deploy":
        return f"deploy:{a.get('card')}"
    if v == "attach_don":
        return f"attach_don:{a.get('qty')}->{a.get('to') or '?'}"
    if v == "attack":
        return "attack:LEADER" if a.get("target_is_leader") else "attack:BODY"
    if v == "counter":
        return f"counter:{a.get('card')}({a.get('value')})"
    if v == "activate_don":
        return f"activate_don:{a.get('qty')}"
    if v == "end_turn":
        return None
    if v == "effect_deploy":
        return f"effect_deploy:{a.get('card')}"
    if v == "effect_top_life":
        return f"effect_top_life:{a.get('source_card')}"
    if v == "effect_send_life_to_hand":
        return f"send_life:{a.get('source_card')}({a.get('qty')})"
    if v == "effect_attach_don":
        rested = "R" if a.get("rested") else ""
        return f"effect_attach_don:{a.get('qty')}{rested}->{a.get('to') or '?'}"
    if v == "effect_revive":
        return f"effect_revive:{a.get('card')}"
    if v == "effect_add_to_life":
        return f"add_to_life:{a.get('card')}"
    if v == "effect_draw_card":
        return f"draw:{a.get('qty') or 1}"
    if v == "effect":
        first = (a.get("cards") or [None])[0]
        if first is None:
            return None
        return f"effect:{first}"
    return f"{v}"


def split_main_and_existing_board(
    actions: list[dict],
    turn_player: str,
    turn_player_leader: str,
    drop_verbs: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Walk actions and split into (main_play, existing_board_swings).

    Main play = turn-player's plays, DON spend, leader-effect consequences,
    and attacks whose attacker was deployed THIS turn (or is the leader).
    Existing-board swings = turn-player's swings with characters deployed on
    prior turns.

    Opponent-controlled reactive actions (e.g. an opponent card's on-destroy
    draw firing during the turn-player's turn) are dropped from both views.
    """
    deployed_this_turn: set[str] = {turn_player_leader}
    main: list[str] = []
    existing_board: list[str] = []
    for a in actions:
        v = a.get("verb")
        tok = action_token(a, drop_verbs=drop_verbs)
        if tok is None:
            continue
        player = a.get("player")
        if player and turn_player and player != turn_player:
            continue
        if v in ("deploy", "effect_deploy"):
            cid = a.get("card")
            if cid:
                deployed_this_turn.add(cid)
            main.append(tok)
        elif v in MAIN_PLAY_VERBS:
            main.append(tok)
        elif v == "attack":
            attacker = a.get("attacker")
            if attacker in deployed_this_turn:
                main.append(tok)
            else:
                existing_board.append(tok)
        else:
            existing_board.append(tok)
    return main, existing_board


def token_view(tok: str, leader_id: str | None = None) -> tuple[str | None, str]:
    """Return (card_id_for_thumbnail, short_label) for one token.

    `leader_id` (if given) is the opponent's leader id, used as the thumbnail
    for `attack:LEADER` tokens so reports show the attacked leader's art.
    """
    if tok.startswith("deploy:"):
        return tok.split(":", 1)[1], "play"
    if tok.startswith("effect_deploy:"):
        return tok.split(":", 1)[1], "leader plays"
    if tok == "attack:LEADER":
        return leader_id, "attack leader"
    if tok == "attack:BODY":
        return None, "attack body"
    if tok.startswith("counter:"):
        body = tok.split(":", 1)[1]
        cid, val = body.rstrip(")").split("(")
        return cid, f"counter -{val}"
    if tok.startswith("attach_don:"):
        body = tok.split(":", 1)[1]
        qty, target = body.split("->", 1)
        return (target if target != "?" else None), f"+{qty} DON"
    if tok.startswith("effect_attach_don:"):
        body = tok.split(":", 1)[1]
        qty, target = body.split("->", 1)
        return (target if target != "?" else None), f"+{qty} DON"
    if tok.startswith("effect_top_life:"):
        return None, "take top life"
    if tok.startswith("draw:"):
        n = tok.split(":", 1)[1]
        return None, f"draw {n}"
    if tok.startswith("send_life:"):
        body = tok.split(":", 1)[1]
        src, rest = body.split("(", 1)
        n = rest.rstrip(")")
        return src, f"send {n} life"
    if tok.startswith("effect_revive:"):
        return tok.split(":", 1)[1], "revive"
    if tok.startswith("add_to_life:"):
        return tok.split(":", 1)[1], "+ to life"
    if tok.startswith("activate_don:"):
        return None, f"activate {tok.split(':',1)[1]} DON"
    if tok.startswith("effect:"):
        cid = tok.split(":", 1)[1]
        return (cid if cid != "None" else None), "effect"
    return None, tok
