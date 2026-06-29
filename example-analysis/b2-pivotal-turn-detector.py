#!/usr/bin/env python3
"""B2 — pivotal-turn detector on losing replays.

For a chosen losing replay, identifies the single turn where the loser's win
probability dropped most sharply — the decision that lost the game.

Method:
  1. Build a "state -> win-rate" lookup table over the FULL matchup corpus.
     State key (per loser turn):
       (going_1st, turn_number, life_bucket, hand_bucket, board_chars_bucket)
     Buckets are coarse to keep per-cell sample counts meaningful.
  2. For the target replay, compute the loser's WP at the start of each of
     their turns by looking up the table.
  3. Pick the consecutive loser-turn pair with the largest negative ΔWP.
  4. Render markdown:
       - per-turn WP table
       - pivotal turn highlighted with the loser's action sequence
       - top-3 winning alternative signatures from the same state
       - opponent-trigger flag (variance, not pilot error)

Usage:
    MANTRA_VAULT_ROOT=~/vault/replays \\
        python3 b2-pivotal-turn-detector.py OP08-098 OP16-080 \\
            --out-dir ./pivotal-turn \\
            [--replay path/to/specific.json]

If no --replay is given, the first losing replay encountered for the chosen
leader in the corpus is analyzed (handy for smoke-testing).

Output: `<out-dir>/<loser>-vs-<opp>-<replay-basename>.md`.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mantra.analyzer.action_token import split_main_and_existing_board
from mantra.analyzer.assets import available_assets_in, ensure_assets
from mantra.analyzer.matchup_lookup import matchup_folder_either_order, vault_root
from mantra.analyzer.render import (
    collect_card_ids_from_sigs,
    render_vault_cell,
)
from mantra.analyzer.replay_loader import (
    load_matchup_folder,
    player_for_leader,
)

MIN_CELL_SAMPLES = 5
SIG_LEN = 6


# ---------- state extraction ----------

def life_bucket(life):
    if life is None: return "?"
    if life >= 4: return "4+"
    if life >= 2: return "2-3"
    if life >= 1: return "1"
    return "0"


def hand_bucket(n):
    if n is None: return "?"
    if n <= 3: return "0-3"
    if n <= 6: return "4-6"
    return "7+"


def board_bucket(n):
    if n is None: return "?"
    if n == 0: return "0"
    if n <= 2: return "1-2"
    if n <= 4: return "3-4"
    return "5+"


def _snapshot_state(turn, target_player):
    life = hand = board = None
    for a in turn.get("actions", []):
        if a.get("player") != target_player:
            continue
        v = a.get("verb")
        if v == "life_snapshot" and life is None:
            life = a.get("life")
        elif v == "hand_snapshot" and hand is None:
            hand = len(a.get("cards", []))
        elif v == "board_snapshot" and board is None:
            board = len(a.get("cards", []))
        if life is not None and hand is not None and board is not None:
            break
    if life is None and hand is None and board is None:
        return None
    return {"life": life, "hand": hand, "board": board}


def turn_state(parsed, turn_idx, target_player):
    """OPBounty emits hand/board/life snapshots at the END of the active
    player's turn, capturing post-turn state for BOTH players. So the target
    player's state at the START of their own turn N lives in turn N-1's
    snapshots. For turn 0, fall back to that turn's own snapshots."""
    turns = parsed.get("turns", [])
    if turn_idx < 0 or turn_idx >= len(turns):
        return None
    if turn_idx == 0:
        return _snapshot_state(turns[0], target_player)
    s = _snapshot_state(turns[turn_idx - 1], target_player)
    if s is not None:
        return s
    return _snapshot_state(turns[turn_idx], target_player)


def state_key(going_1st, turn_no, state):
    return (
        "1st" if going_1st else "2nd",
        turn_no,
        life_bucket(state.get("life")),
        hand_bucket(state.get("hand")),
        board_bucket(state.get("board")),
    )


# ---------- corpus state table ----------

def build_state_table(parsed_all, leader_id, opp_leader_id):
    table = defaultdict(lambda: {"wins": 0, "total": 0, "sigs": []})
    for p in parsed_all:
        my_player = player_for_leader(p, leader_id)
        opp_player = player_for_leader(p, opp_leader_id)
        if not my_player or not opp_player:
            continue
        winner = p.get("winner")
        if winner not in (my_player, opp_player):
            continue
        won = (winner == my_player)
        going_1st = (p.get("first") == my_player)
        for idx, turn in enumerate(p.get("turns", [])):
            if turn.get("player") != my_player:
                continue
            state = turn_state(p, idx, my_player)
            if state is None:
                continue
            key = state_key(going_1st, turn.get("turn", -1), state)
            table[key]["total"] += 1
            if won:
                table[key]["wins"] += 1
            main_sig, _ = split_main_and_existing_board(
                turn.get("actions", []), my_player, leader_id
            )
            sig = tuple(main_sig[:SIG_LEN])
            table[key]["sigs"].append((sig, won))
    return table


# ---------- per-replay WP ----------

def loser_turn_states(parsed, loser_player, loser_leader):
    going_1st = (parsed.get("first") == loser_player)
    out = []
    for idx, turn in enumerate(parsed.get("turns", [])):
        if turn.get("player") != loser_player:
            continue
        state = turn_state(parsed, idx, loser_player)
        if state is None:
            continue
        main_sig, bg_sig = split_main_and_existing_board(
            turn.get("actions", []), loser_player, loser_leader
        )
        opp_triggers = sum(
            1 for a in turn.get("actions", [])
            if a.get("verb") == "effect_activate_trigger"
            and a.get("player") and a.get("player") != loser_player
        )
        out.append({
            "turn_no": turn.get("turn"),
            "state": state,
            "going_1st": going_1st,
            "sig_main": tuple(main_sig[:SIG_LEN]),
            "sig_bg": tuple(bg_sig[:SIG_LEN]),
            "opp_triggers": opp_triggers,
        })
    return out


def wp_for_turn(state_table, going_1st, turn_no, state):
    key = state_key(going_1st, turn_no, state)
    cell = state_table.get(key)
    if not cell or cell["total"] < MIN_CELL_SAMPLES:
        return None, cell["total"] if cell else 0
    return cell["wins"] / cell["total"], cell["total"]


def find_pivotal_turn(turns_info, wps):
    best_idx = None
    best_drop = 0.0
    for i in range(len(wps) - 1):
        a = wps[i][0]
        b = wps[i + 1][0]
        if a is None or b is None:
            continue
        drop = a - b
        if drop > best_drop:
            best_drop = drop
            best_idx = i + 1
    return best_idx


def alternative_lines(state_table, going_1st, turn_no, state, top_k=3):
    key = state_key(going_1st, turn_no, state)
    cell = state_table.get(key)
    if not cell:
        return []
    sig_stats = defaultdict(lambda: [0, 0])
    for sig, won in cell["sigs"]:
        sig_stats[sig][1] += 1
        if won:
            sig_stats[sig][0] += 1
    ranked = sorted(sig_stats.items(), key=lambda kv: -kv[1][1])
    return [(sig, w, n) for sig, (w, n) in ranked[:top_k]]


# ---------- report ----------

def find_first_loss(parsed_all, leader_id):
    for p in parsed_all:
        my_player = player_for_leader(p, leader_id)
        if not my_player:
            continue
        if p.get("winner") and p.get("winner") != my_player:
            return p
    return None


def build_report(parsed, loser_leader, opp_leader, state_table,
                 available_assets, assets_dir_rel):
    loser_player = player_for_leader(parsed, loser_leader)
    going_1st = (parsed.get("first") == loser_player)
    turns_info = loser_turn_states(parsed, loser_player, loser_leader)
    wps = [
        wp_for_turn(state_table, going_1st, t["turn_no"], t["state"])
        for t in turns_info
    ]
    pivot_idx = find_pivotal_turn(turns_info, wps)
    md = parsed.get("_metadata", {})

    L = []
    L.append(f"# Pivotal-turn review — {loser_leader} loss vs {opp_leader}")
    L.append("")
    L.append(f"**Replay:** `{md.get('_local_path') or md.get('path', '?')}`")
    L.append(f"**Week:** {md.get('week', '?')}  ·  **Loser bounty:** {md.get('loser_bounty', '?')}  ·  **Winner bounty:** {md.get('winner_bounty', '?')}")
    L.append(f"**Going:** {'1st' if going_1st else '2nd'}  ·  **Turns played:** {len(turns_info)}")
    L.append("")
    L.append("**Method:** Built a coarse `(turn, life, hand, board)` state table from "
             f"the {loser_leader}-vs-{opp_leader} corpus, then estimated loser WP at "
             "the start of each of their turns. Pivotal turn = largest negative ΔWP "
             f"between consecutive turns. Cells with <{MIN_CELL_SAMPLES} samples are skipped.")
    L.append("")

    L.append("## Per-turn WP")
    L.append("")
    L.append("| Turn | Life | Hand | Board | WP (loser) | Sample n | ΔWP | Note |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---|")
    prev_wp = None
    for i, t in enumerate(turns_info):
        wp, n = wps[i]
        wp_s = f"{wp*100:.0f}%" if wp is not None else "—"
        d_s = ""
        if wp is not None and prev_wp is not None:
            d = wp - prev_wp
            arrow = "↓" if d < -0.05 else "↑" if d > 0.05 else "→"
            d_s = f"{arrow} {d*100:+.0f}pp"
        note = ""
        if pivot_idx == i:
            note = "**◀ pivotal turn**"
        if t["opp_triggers"]:
            note += (" · " if note else "") + f"⚡{t['opp_triggers']} opp trigger"
        L.append(
            f"| {t['turn_no']} | {t['state'].get('life','?')} | {t['state'].get('hand','?')} | "
            f"{t['state'].get('board','?')} | {wp_s} | {n} | {d_s} | {note} |"
        )
        if wp is not None:
            prev_wp = wp

    L.append("")
    if pivot_idx is None:
        L.append("## Pivotal turn")
        L.append("")
        L.append("_No turn had a measurable WP drop — either every cell was below the "
                 f"sample threshold ({MIN_CELL_SAMPLES}), or the loss was gradual rather "
                 "than a single decision collapse._")
        return "\n".join(L) + "\n"

    pivotal_turn = turns_info[pivot_idx]
    prior_turn = turns_info[pivot_idx - 1]
    pre_wp = wps[pivot_idx - 1][0]
    post_wp = wps[pivot_idx][0]

    L.append("## Pivotal turn")
    L.append("")
    L.append(
        f"**Loser's turn {prior_turn['turn_no']}** is the pivotal turn — "
        f"WP at start of that turn was **{pre_wp*100:.0f}%**, and by the start of "
        f"their next turn (turn {pivotal_turn['turn_no']}) it had fallen to "
        f"**{post_wp*100:.0f}%** (Δ {(post_wp - pre_wp)*100:+.0f}pp)."
    )
    L.append("")
    L.append(
        f"State at start of turn {prior_turn['turn_no']}: "
        f"life **{prior_turn['state'].get('life','?')}**, "
        f"hand **{prior_turn['state'].get('hand','?')}**, "
        f"board **{prior_turn['state'].get('board','?')}** "
        f"character{'s' if (prior_turn['state'].get('board') or 0) != 1 else ''}."
    )
    L.append("")

    if pivotal_turn["opp_triggers"]:
        L.append(
            f"⚠️ The opponent fired **{pivotal_turn['opp_triggers']}** trigger"
            f"{'s' if pivotal_turn['opp_triggers'] != 1 else ''} on this turn. "
            "Part of the WP drop may be variance, not pilot error."
        )
        L.append("")

    L.append("### What the loser played")
    L.append("")
    sig = prior_turn["sig_main"]
    if not sig:
        L.append("_(no main-play actions captured this turn)_")
    else:
        cell = render_vault_cell(
            sig, available_assets, assets_dir_rel,
            leader_id_for_attack=opp_leader,
        )
        L.append(cell)
    L.append("")

    L.append("### Top 3 alternative lines from the corpus")
    L.append("")
    L.append(
        f"From the same state (turn {prior_turn['turn_no']}, "
        f"life {prior_turn['state'].get('life')}, "
        f"hand {prior_turn['state'].get('hand')}, "
        f"board {prior_turn['state'].get('board')} characters, going {'1st' if going_1st else '2nd'}), "
        "the most-played action signatures across the corpus and their win rates:"
    )
    L.append("")
    alts = alternative_lines(state_table, going_1st, prior_turn["turn_no"], prior_turn["state"], top_k=3)
    if not alts:
        L.append("_No alternative signatures in the corpus from this state._")
    else:
        L.append("| Freq | Wins | WR | Line |")
        L.append("|---:|---:|---:|---|")
        for sig, w, n in alts:
            wr = (w / n * 100) if n else 0
            cell = render_vault_cell(
                sig, available_assets, assets_dir_rel,
                leader_id_for_attack=opp_leader,
            ) if sig else "(empty turn)"
            L.append(f"| {n} | {w} | {wr:.0f}% | {cell} |")
    L.append("")

    L.append("## Caveats")
    L.append("")
    L.append("- **State buckets are coarse.** Cells differ on `(turn, life, hand_bucket, board_bucket)`. Two states in the same cell may not be strategically identical.")
    L.append(f"- **WP estimates need ≥{MIN_CELL_SAMPLES} samples per cell** to be shown. Sparse cells (smaller corpus) will read as `—`.")
    L.append("- **WP is sampled at the START of the loser's turns.** The drop between consecutive loser turns conflates the loser's decisions AND the opponent's intervening turn. Read the alternatives table against the loser's actual line to see whether the gap is plausibly the loser's decision vs opponent pressure.")
    L.append("- **'Loss' here is the parser's `winner` field.** Truncated replays without a winner are skipped upstream.")
    L.append("- **Pivotal turn ≠ only mistake.** Earlier turns can still contain errors that compound; this report just identifies the largest single-turn collapse.")
    L.append("- **Opponent triggers** flagged with ⚡ are variance, not pilot decisions — read those rows accordingly.")

    return "\n".join(L) + "\n"


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("leader_id", help="Loser leader card id, e.g. OP08-098")
    ap.add_argument("opp_leader_id", help="Opponent leader card id, e.g. OP16-080")
    ap.add_argument("--replay", default=None,
                    help="Specific replay JSON path to analyze. "
                         "If omitted, the first losing replay encountered in the corpus is used.")
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)),
                    help="Output directory for the report markdown. "
                         "Defaults to the script's own directory.")
    ap.add_argument("--assets-subdir", default="assets/pivotal-turn",
                    help="Sub-path used for asset images. Resolved relative to --out-dir.")
    ap.add_argument("--extra-asset-source", action="append", default=[],
                    help="Additional local cache directory to scan for card art "
                         "before downloading. May be repeated.")
    args = ap.parse_args()

    root = vault_root()
    folder = matchup_folder_either_order(args.leader_id, args.opp_leader_id, root=root)
    if not folder:
        print(
            f"No matchup folder for {args.leader_id}-vs-{args.opp_leader_id} under {root}.\n"
            f"Run `snapshot_replays(leader='{args.leader_id}', opponent='{args.opp_leader_id}')` "
            "via the mantra MCP first.",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed_all = load_matchup_folder(folder)
    print(f"Loaded {len(parsed_all)} replays from {folder}")
    state_table = build_state_table(parsed_all, args.leader_id, args.opp_leader_id)
    print(f"State table has {len(state_table)} unique cells")

    if args.replay:
        target_parsed = json.load(open(args.replay))
        target_parsed.setdefault("_metadata", {})["_local_path"] = args.replay
    else:
        target_parsed = find_first_loss(parsed_all, args.leader_id)
        if not target_parsed:
            print(f"No losing replay for {args.leader_id} found in corpus.", file=sys.stderr)
            sys.exit(1)

    target_path_str = target_parsed.get("_metadata", {}).get("_local_path", "?")
    print(f"Analyzing {target_path_str}")

    assets_dir_abs = os.path.join(os.path.expanduser(args.out_dir), args.assets_subdir)
    loser_player = player_for_leader(target_parsed, args.leader_id)
    going_1st = (target_parsed.get("first") == loser_player)

    sigs_to_collect = []
    for turn_info in loser_turn_states(target_parsed, loser_player, args.leader_id):
        sigs_to_collect.append(turn_info["sig_main"])
        for sig, _, _ in alternative_lines(state_table, going_1st, turn_info["turn_no"], turn_info["state"]):
            sigs_to_collect.append(sig)
    needed = collect_card_ids_from_sigs(
        sigs_to_collect,
        extra_ids={args.leader_id, args.opp_leader_id},
        leader_id_for_attack=args.opp_leader_id,
    )
    copied, downloaded, missing = ensure_assets(
        needed, assets_dir_abs, extra_sources=args.extra_asset_source,
    )
    print(f"Assets: {copied} copied, {downloaded} downloaded, {len(missing)} missing")
    available = available_assets_in(assets_dir_abs)

    report = build_report(
        target_parsed, args.leader_id, args.opp_leader_id, state_table,
        available, args.assets_subdir,
    )
    os.makedirs(os.path.expanduser(args.out_dir), exist_ok=True)
    basename = os.path.splitext(os.path.basename(target_path_str))[0]
    out_path = os.path.join(
        os.path.expanduser(args.out_dir),
        f"{args.leader_id}-vs-{args.opp_leader_id}-{basename}.md",
    )
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
