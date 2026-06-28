#!/usr/bin/env python3
"""Kalgara-vs-Teach: what does Kalgara do on its 5-DON turn?

Loads every cached OP08-098 vs OP16-080 replay (standard queue) and inspects
each Kalgara turn where don_at_start == 5. Builds action signatures, ranks by
frequency, splits by 1st/2nd and by Kalgara won/lost.

The signature for a 5-DON turn is the sequence of meaningful actions:
  - deploy:<card_id>
  - attach_don:<qty>->LEADER|<card_id>
  - attack:LEADER  (we don't care which board target — Kalgara's job is life)
  - attack:BODY
  - effect:<source_card>:short_text
Snapshot-style lines (Hand/Trash/Board/Life) and combat-resolve / hit lines
are dropped; they're either bookkeeping or are inferable from the actions.

Output: this script + a paired markdown report.
"""
import json, os, glob, re
from collections import Counter, defaultdict

KALGARA = "OP08-098"
TEACH = "OP16-080"
VAULT = os.path.expanduser(os.environ.get("OPBOUNTY_VAULT_ROOT", "~/opbounty-replays"))
DIR = os.path.join(VAULT, "OP08-098-vs-OP16-080")
REPORT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalgara-vs-teach-5don-turns.md")

# Card name lookup — populated from the deck-list metadata so the report can
# show e.g. "play 5c Wyper (OP15-114)" without a separate database.
NAME = {}

DROP_VERBS = {
    "hand_snapshot", "trash_snapshot", "board_snapshot", "life_snapshot",
    "draw_card_count", "combat_resolve", "hit_for", "attack_fails",
    "draw_don", "block", "destroyed", "draw_card", "hand_pre_mulligan",
    "draw_rested_don",  # these are leader-effect ramps; not core action choice
}


def action_token(a: dict) -> str | None:
    v = a.get("verb")
    if v in DROP_VERBS:
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
    if v == "effect":
        # Compress effect text to a short key on the source-card id
        return f"effect:{(a.get('cards') or [None])[0]}"
    return f"{v}"


def kalgara_5don_turns(parsed: dict):
    """Yield (replay_id, turn_idx, kalgara_won?, kalgara_first?, actions_signature_list)
    for every turn where it's Kalgara's player on the move with 5 DON at start."""
    kalgara_player = None
    teach_player = None
    for n, info in parsed.get("players", {}).items():
        if info.get("leader") == KALGARA: kalgara_player = n
        if info.get("leader") == TEACH:   teach_player = n
    if not kalgara_player or not teach_player:
        return
    won = parsed.get("winner") == kalgara_player
    first = parsed.get("first") == kalgara_player
    for turn in parsed.get("turns", []):
        if turn.get("player") != kalgara_player:
            continue
        if turn.get("don_at_start") != 5:
            continue
        tokens = []
        for a in turn.get("actions", []):
            tok = action_token(a)
            if tok is not None:
                tokens.append(tok)
        yield (won, first, tuple(tokens), turn)


def harvest_names(parsed: dict):
    md = parsed.get("_metadata", {})
    # extract Nx<id> entries from deck strings to seed a flat id->name? we don't have
    # names in metadata — use the inline drew/deploy cards which DO carry names.
    for t in parsed.get("turns", []):
        for a in t.get("actions", []):
            for cid in (a.get("cards") or []):
                NAME.setdefault(cid, cid)
            for k in ("card","to","attacker","source_card"):
                cid = a.get(k)
                if cid: NAME.setdefault(cid, cid)


def pretty(token: str) -> str:
    """Make tokens slightly more readable for the report (uses card ids)."""
    return token


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.json")))
    parsed_all = []
    for f in files:
        try:
            parsed_all.append(json.load(open(f)))
        except Exception:
            pass
    print(f"Loaded {len(parsed_all)} parsed replays")

    # Validate: winner attribution coverage
    have_winner = sum(1 for p in parsed_all if p.get("winner"))
    print(f"Winner attributed: {have_winner}/{len(parsed_all)}")

    # Quick game-level Kalgara win-rate
    kalgara_wins = 0
    kalgara_games = 0
    for p in parsed_all:
        for n, info in p.get("players", {}).items():
            if info.get("leader") == KALGARA:
                kalgara_games += 1
                if p.get("winner") == n:
                    kalgara_wins += 1
                break
    wr = (kalgara_wins / kalgara_games * 100) if kalgara_games else 0
    print(f"Kalgara WR in sample: {kalgara_wins}/{kalgara_games} = {wr:.1f}%")

    # Collect 5-DON turns
    by_sig = Counter()
    sig_wins = Counter()
    by_sig_first = defaultdict(Counter)
    by_sig_first_wins = defaultdict(Counter)
    sample_paths = defaultdict(list)
    no_5don = 0
    for p in parsed_all:
        had_5don = False
        for won, first, sig, _turn in kalgara_5don_turns(p):
            had_5don = True
            key = "1st" if first else "2nd"
            by_sig[sig] += 1
            by_sig_first[key][sig] += 1
            if won:
                sig_wins[sig] += 1
                by_sig_first_wins[key][sig] += 1
            md = p.get("_metadata", {})
            if len(sample_paths[sig]) < 3:
                sample_paths[sig].append(md.get("path", "?"))
        if not had_5don:
            no_5don += 1
    print(f"Replays with at least one Kalgara 5-DON turn: {len(parsed_all)-no_5don}/{len(parsed_all)}")
    print(f"Distinct 5-DON action signatures: {len(by_sig)}")

    # Common prefix analysis: instead of full-sequence signatures (which tend to
    # be unique), also bucket by the first 3 non-trivial actions.
    short_by_sig = Counter()
    short_wins = Counter()
    short_by_first = defaultdict(Counter)
    short_by_first_wins = defaultdict(Counter)
    short_samples = defaultdict(list)
    for p in parsed_all:
        for won, first, sig, _turn in kalgara_5don_turns(p):
            shortsig = tuple(sig[:5])  # first 5 meaningful tokens
            short_by_sig[shortsig] += 1
            key = "1st" if first else "2nd"
            short_by_first[key][shortsig] += 1
            if won:
                short_wins[shortsig] += 1
                short_by_first_wins[key][shortsig] += 1
            md = p.get("_metadata", {})
            if len(short_samples[shortsig]) < 3:
                short_samples[shortsig].append(md.get("path", "?"))

    # Write report
    lines = []
    lines.append(f"# Kalgara vs by Teach — 5-DON Turn Analysis")
    lines.append("")
    lines.append(f"**Date:** 2026-06-28")
    lines.append(f"**Source:** OPBounty replay collection — standard queue (game_mode=0), top-200 ladder or 3000+ bounty pilots only.")
    lines.append(f"**Replays loaded:** {len(parsed_all)}")
    lines.append(f"**With at least one Kalgara 5-DON turn:** {len(parsed_all)-no_5don}")
    lines.append(f"**Kalgara win rate in this sample:** {kalgara_wins}/{kalgara_games} = {wr:.1f}%")
    lines.append("")
    lines.append("**Method:** For each replay, find Kalgara's turn whose `don_at_start == 5` (the first 5-DON turn, i.e. turn 3 going 2nd or turn 4 going 1st). Take the action sequence on that turn — `deploy`, `attach_don`, `attack` (vs leader/body), `counter`, `effect:source_card`. Group by the first 5 meaningful actions ('short signature'). Snapshot lines and combat-resolve lines are dropped — they're bookkeeping, not decisions.")
    lines.append("")
    lines.append("Note: card-id readability is left to the reader; e.g. `OP15-114` = 5c Wyper, `OP08-098` = Kalgara leader, `OP08-099` = 4c New Kalgara, `OP06-111` = Braham, `OP05-106` = Shura, `OP05-117` = Counter (Earth Won't Lose), `EB03-053` = Zeus.")
    lines.append("")
    lines.append("## Top 5-DON action openings (first 5 meaningful tokens)")
    lines.append("")
    lines.append("| Freq | Wins | WR | Tokens | Sample replays |")
    lines.append("|---:|---:|---:|---|---|")
    for sig, n in short_by_sig.most_common(20):
        w = short_wins[sig]
        wr = (w/n*100) if n else 0
        toks = " · ".join(sig) if sig else "(empty turn)"
        samps = "<br>".join(short_samples[sig])
        lines.append(f"| {n} | {w} | {wr:.0f}% | `{toks}` | <sub>{samps}</sub> |")
    lines.append("")
    lines.append("## 1st vs 2nd split (top 10 each)")
    lines.append("")
    for key in ("1st","2nd"):
        lines.append(f"### Going **{key}**  ({sum(short_by_first[key].values())} 5-DON turns)")
        lines.append("")
        lines.append("| Freq | Wins | WR | Tokens |")
        lines.append("|---:|---:|---:|---|")
        for sig, n in short_by_first[key].most_common(10):
            w = short_by_first_wins[key][sig]
            wr2 = (w/n*100) if n else 0
            toks = " · ".join(sig) if sig else "(empty turn)"
            lines.append(f"| {n} | {w} | {wr2:.0f}% | `{toks}` |")
        lines.append("")
    lines.append("## Card-level: what gets PLAYED on the 5-DON turn?")
    lines.append("")
    deploys = Counter()
    deploy_wins = Counter()
    for p in parsed_all:
        for won, first, sig, _turn in kalgara_5don_turns(p):
            for tok in sig:
                if tok.startswith("deploy:"):
                    cid = tok.split(":")[1]
                    deploys[cid] += 1
                    if won: deploy_wins[cid] += 1
    lines.append("| Card id | Plays | Wins-when-played | WR |")
    lines.append("|---|---:|---:|---:|")
    for cid, n in deploys.most_common(20):
        w = deploy_wins[cid]
        wr3 = (w/n*100) if n else 0
        lines.append(f"| `{cid}` | {n} | {w} | {wr3:.0f}% |")
    lines.append("")
    lines.append("## Card-level: what's DON-attached on the 5-DON turn?")
    lines.append("")
    targets = Counter()
    target_wins = Counter()
    for p in parsed_all:
        for won, first, sig, _turn in kalgara_5don_turns(p):
            for tok in sig:
                if tok.startswith("attach_don:"):
                    # token = attach_don:<qty>-><target>
                    target = tok.split("->",1)[1]
                    qty = tok.split(":")[1].split("->")[0]
                    targets[(qty,target)] += 1
                    if won: target_wins[(qty,target)] += 1
    lines.append("| Qty | Target | Times | Wins | WR |")
    lines.append("|---:|---|---:|---:|---:|")
    for (qty,t), n in targets.most_common(20):
        w = target_wins[(qty,t)]
        wr4 = (w/n*100) if n else 0
        lines.append(f"| {qty} | `{t}` | {n} | {w} | {wr4:.0f}% |")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- **Top-MMR sample only.** OPBounty only uploads replays from top-200 / 3000+ bounty pilots. This is high-skill play, not ladder average.")
    lines.append("- **Standard queue (game_mode=0)** only. Other queue codes excluded.")
    lines.append("- **Truncated logs** that didn't complete a 5-DON Kalgara turn are silently dropped. Truncation appears in newer-client logs that emit RZ1 state frames and may end mid-game.")
    lines.append("- **Action ordering** in the log reflects the in-game action timeline, but it's possible for some effect lines to land out of natural order (e.g. an effect prints AFTER the attack it modified). Treat the first-3 ordering as descriptive of opening intent, not strict sequence.")
    lines.append("- **`don_at_start == 5`** picks Kalgara's turn 4 going 1st OR turn 3 going 2nd — but it can also pick a later turn if Kalgara was DON-returned. Filtering to first-occurrence-per-replay would be cleaner; current code reports all 5-DON turns. (For Kalgara most games only have one 5-DON turn since there's no return-DON effect in the deck.)")
    open(REPORT, "w").write("\n".join(lines))
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
