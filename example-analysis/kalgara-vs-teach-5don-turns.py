#!/usr/bin/env python3
"""Kalgara-vs-Teach: what does Kalgara do on its 5-DON turn?

Loads every cached OP08-098 vs OP16-080 replay (standard queue) and inspects
each Kalgara turn where don_at_start == 5. Builds action signatures, ranks by
frequency, focuses on the 1st-going split (Kalgara has no DON acceleration so
5-DON-on-2nd is structurally impossible).

The signature for a 5-DON turn is the sequence of meaningful actions:
  - deploy:<card_id>                 (hard-paid play from hand)
  - effect_deploy:<card_id>          (leader-effect play, e.g. Kalgara's
                                      'Deploy from hand' after attack)
  - attach_don:<qty>-><id>           (player-driven DON attach)
  - effect_attach_don:<qty>[R]-><id> (effect-driven, e.g. Nami / 5c Wyper)
  - attack:LEADER | attack:BODY
  - counter:<id>(<value>)
  - effect_top_life:<src>, send_life:<src>(<qty>), effect_revive:<id>, ...
Snapshot/combat-resolve/hit lines and informational effects are dropped.

Output: two markdown reports.
  * Repo (GitHub-readable): plain card IDs.
  * Vault (Obsidian, thumbnails): two-row HTML cells with card art on top
    and short text labels below — produces a visual strip per row.
"""
import json, os, glob, shutil, ssl, sys, urllib.request, urllib.error
from collections import Counter, defaultdict

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

KALGARA = "OP08-098"
TEACH = "OP16-080"

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.expanduser(
    os.environ.get("MANTRA_VAULT_ROOT")
    or os.environ.get("OPBOUNTY_VAULT_ROOT")
    or "~/Documents/travisobsidian/optcg-op16/replays"
)
DIR = os.path.join(VAULT_ROOT, "OP08-098-vs-OP16-080")

REPO_REPORT = os.path.join(REPO_DIR, "kalgara-vs-teach-5don-turns.md")
VAULT_REPORT = os.path.expanduser(
    "~/Documents/travisobsidian/optcg-op16/replay-analysis/kalgara-vs-teach-5don-turns-2026-06-28.md"
)
ASSETS_DIR_ABS = os.path.expanduser(
    "~/Documents/travisobsidian/optcg-op16/replay-analysis/assets/kalgara-vs-teach"
)
# Relative path used inside the vault markdown so Obsidian resolves it.
ASSETS_DIR_REL = "assets/kalgara-vs-teach"

# Existing asset caches to check before downloading.
ASSET_SOURCES = [
    os.path.expanduser("~/Documents/travisobsidian/optcg-op16/assets/kalgara-explore"),
    os.path.expanduser("~/Documents/travisobsidian/optcg-op16/assets/leader-art"),
    os.path.expanduser("~/Documents/travisobsidian/optcg-op16/assets/boa-explore"),
    os.path.expanduser("~/Documents/travisobsidian/optcg-op16/assets/kalgara-top5"),
]
CARD_ART_URL = "https://en.onepiece-cardgame.com/images/cardlist/card/{cid}.png"


DROP_VERBS = {
    "hand_snapshot", "trash_snapshot", "board_snapshot", "life_snapshot",
    "draw_card_count", "combat_resolve", "hit_for", "attack_fails",
    "draw_don", "block", "destroyed", "draw_card", "hand_pre_mulligan",
    "draw_rested_don",
    "effect_reveal_draw",        # Kalgara mill reveal; informational
    "effect_block_draw",         # Teach's anti-draw lock; informational
    "effect_activate_trigger",   # trigger reveal; informational
    "effect_activate_counter",   # counter captured by `counter`
    "effect_redirect_attack",    # attack target swap; bookkeeping
    "effect_topdeck", "effect_set", "effect_flip_life",
    "effect_buff", "effect_nullify", "effect_destroy", "effect_counter",
    "effect_trash", "effect_trash_from_life", "effect_trash_remaining",
    "effect_rest", "effect_rest_don",
    # effect_top_life and effect_draw_card are KEPT — they're consequences of
    # the play (Kalgara leader life-trash, 4c-Kalgara/Wyper on-deploy draw)
    # that a player wants to see in the action strip.
}

# Verbs that are part of "the main play" on a 5-DON turn: hard-paid plays,
# leader-driven plays + their immediate consequences, and DON spend. Attacks
# are conditional — included only if the attacker was deployed THIS turn.
MAIN_PLAY_VERBS = {
    "deploy", "effect_deploy", "attach_don", "effect_attach_don",
    "counter", "effect_top_life", "effect_send_life_to_hand",
    "effect_draw_card", "effect_revive", "effect_add_to_life",
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


def _split_main_and_background(actions: list[dict], turn_player: str) -> tuple[list[str], list[str]]:
    """Walk the action list and emit two parallel token sequences.

    Main play = the turn-player's plays, DON spend, leader-effect
    consequences, and attacks whose attacker was deployed THIS turn (or is
    the leader). Existing-board swings = the turn-player's swings with
    characters deployed on prior turns.

    Actions belonging to the OPPONENT (reactive triggers like a destroyed
    Van Augur's on-destroy draw) are dropped entirely from both views —
    they're not the turn player's decisions.

    Order is preserved within each list.
    """
    deployed_this_turn: set[str] = {KALGARA}  # leader is always "this turn's" attacker
    main: list[str] = []
    background: list[str] = []
    for a in actions:
        v = a.get("verb")
        tok = action_token(a)
        if tok is None:
            continue
        # Drop opponent-controlled reactive effects (e.g. Van Augur's
        # on-destroy draw fires during Kalgara's turn; Kalgara didn't decide
        # to draw — the opponent's card did).
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
                background.append(tok)
        else:
            background.append(tok)
    return main, background


def kalgara_5don_turns(parsed: dict):
    """Yield (won, first, main_sig, background_sig, turn).

    `main_sig` is the trimmed main-play token sequence (what the player
    actually does with their 5 DON, plus immediate consequences).
    `background_sig` is the other kept tokens (existing-board swings)."""
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
        main, background = _split_main_and_background(turn.get("actions", []), kalgara_player)
        yield (won, first, tuple(main), tuple(background), turn)


# ---------- token → (card_id_for_thumbnail, label) ----------

def token_view(tok: str) -> tuple[str | None, str]:
    """Return (card_id_for_thumbnail, short_label) for one action token.
    card_id None means the step is text-only (e.g. attack-body, top-life)."""
    if tok.startswith("deploy:"):
        return tok.split(":",1)[1], "play"
    if tok.startswith("effect_deploy:"):
        return tok.split(":",1)[1], "leader plays"
    if tok == "attack:LEADER":
        return TEACH, "attack leader"
    if tok == "attack:BODY":
        return None, "attack body"
    if tok.startswith("counter:"):
        body = tok.split(":",1)[1]
        cid, val = body.rstrip(")").split("(")
        return cid, f"counter -{val}"
    if tok.startswith("attach_don:"):
        body = tok.split(":",1)[1]
        qty, target = body.split("->",1)
        return (target if target != "?" else None), f"+{qty} DON"
    if tok.startswith("effect_attach_don:"):
        body = tok.split(":",1)[1]
        qty, target = body.split("->",1)
        return (target if target != "?" else None), f"+{qty} DON"
    if tok.startswith("effect_top_life:"):
        return None, "take top life"
    if tok.startswith("draw:"):
        n = tok.split(":",1)[1]
        return None, f"draw {n}"
    if tok.startswith("send_life:"):
        body = tok.split(":",1)[1]
        src, rest = body.split("(",1)
        n = rest.rstrip(")")
        return src, f"send {n} life"
    if tok.startswith("effect_revive:"):
        return tok.split(":",1)[1], "revive"
    if tok.startswith("add_to_life:"):
        return tok.split(":",1)[1], "+ to life"
    if tok.startswith("activate_don:"):
        return None, f"activate {tok.split(':',1)[1]} DON"
    if tok.startswith("effect:"):
        cid = tok.split(":",1)[1]
        return (cid if cid != "None" else None), "effect"
    return None, tok


# ---------- asset bootstrap ----------

def ensure_assets(card_ids: set[str]) -> tuple[int, int, list[str]]:
    """Ensure assets/kalgara-vs-teach/<id>.png exists for every id.
    Copies from existing local caches first, falls back to download.
    Returns (copied, downloaded, missing_ids)."""
    os.makedirs(ASSETS_DIR_ABS, exist_ok=True)
    copied = 0
    downloaded = 0
    missing: list[str] = []
    for cid in sorted(card_ids):
        target = os.path.join(ASSETS_DIR_ABS, f"{cid}.png")
        if os.path.exists(target):
            continue
        found_local = None
        for src in ASSET_SOURCES:
            cand = os.path.join(src, f"{cid}.png")
            if os.path.exists(cand):
                found_local = cand
                break
        if found_local:
            shutil.copyfile(found_local, target)
            copied += 1
            continue
        url = CARD_ART_URL.format(cid=cid)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as r:
                data = r.read()
            with open(target, "wb") as f:
                f.write(data)
            downloaded += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            missing.append(cid)
            print(f"  WARN: could not fetch {cid}: {e}", file=sys.stderr)
    return copied, downloaded, missing


def collect_card_ids(sigs: list[tuple]) -> set[str]:
    ids: set[str] = {TEACH, KALGARA}
    for sig in sigs:
        for tok in sig:
            cid, _ = token_view(tok)
            if cid:
                ids.add(cid)
    return ids


# ---------- renderers ----------

def render_repo_cell(sig: tuple) -> str:
    """Repo mode: plain backtick token string, joined with · ."""
    return "`" + " · ".join(sig) + "`" if sig else "(empty turn)"


def render_vault_cell(sig: tuple, available: set[str]) -> str:
    """Vault mode: two-row HTML table — thumbnails on top, labels below.
    Cards missing locally (in `available`) render label-only."""
    if not sig:
        return "(empty turn)"
    thumb_cells = []
    label_cells = []
    for tok in sig:
        cid, label = token_view(tok)
        if cid and cid in available:
            thumb_cells.append(
                f'<td><img src="{ASSETS_DIR_REL}/{cid}.png" width="60"></td>'
            )
        else:
            thumb_cells.append("<td></td>")
        label_cells.append(f"<td>{label}</td>")
    return (
        "<table><tr>" + "".join(thumb_cells) + "</tr>"
        "<tr>" + "".join(label_cells) + "</tr></table>"
    )


# ---------- report builder ----------

def build_report(*, parsed_all, kalgara_wins, kalgara_games, no_5don,
                 short_by_first, short_by_first_wins, short_samples,
                 bg_by_main,
                 deploys, deploy_wins, deploy_kind,
                 targets, target_wins, mode: str, available_assets: set[str]):
    wr = (kalgara_wins / kalgara_games * 100) if kalgara_games else 0
    going_2nd_anom = sum(short_by_first["2nd"].values())

    L: list[str] = []
    L.append("# Kalgara vs Teach — 5-DON Turn Analysis")
    L.append("")
    L.append("**Date:** 2026-06-28")
    L.append("**Source:** OPBounty replay collection — standard queue (game_mode=0), top-200 ladder or 3000+ bounty pilots only.")
    L.append(f"**Replays loaded:** {len(parsed_all)}")
    L.append(f"**With at least one Kalgara 5-DON turn:** {len(parsed_all)-no_5don}")
    L.append(f"**Kalgara win rate in this sample:** {kalgara_wins}/{kalgara_games} = {wr:.1f}%")
    L.append("")
    L.append("**Method:** For each replay, find Kalgara's turn whose `don_at_start == 5`. Take the action sequence on that turn and split it into two strips: a **main play** (cards played this turn, DON spent, attacks with characters deployed this turn, and the consequences of those plays — `effect_top_life`, on-deploy draws, `send_life`, `effect_revive`, `add_to_life`) and **existing-board swings** (attacks with characters that were already on the board before this turn). Group by the first 8 main-play tokens; rows differing only in existing-board swings collapse together. Snapshot, combat-resolve and informational effect lines (trigger reveal, Kalgara's leader reveal-mill) are dropped.")
    L.append("")
    L.append("Card legend (Kalgara core): `OP15-114` = 5c Wyper, `OP08-098` = Kalgara leader, `OP08-099` = 4c New Kalgara, `OP12-099` = leader-effect Kalgara, `OP06-114` = Wyper (rev), `EB03-053` = Zeus/Nami, `OP05-117` = Earth Won't Lose counter.")
    L.append("")
    L.append("## Going 1st — top 10 5-DON openings")
    L.append("")
    L.append(f"**{sum(short_by_first['1st'].values())} 5-DON turns** observed going 1st.")
    L.append("")
    L.append("Each row shows the **main play** (deploys, DON spend, attacks with cards played this turn, and their immediate effects). If the Kalgara player also swung an existing-board character before/after the main play, those existing-board swings are shown in the secondary strip below — they're not part of the 5-DON decision but help contextualize the turn.")
    L.append("")
    L.append("| Freq | Wins | WR | Main play (and existing-board swings) |")
    L.append("|---:|---:|---:|---|")
    for sig, n in short_by_first["1st"].most_common(10):
        w = short_by_first_wins["1st"][sig]
        wr2 = (w/n*100) if n else 0
        bg_top = bg_by_main[sig].most_common(1)
        bg_sig = bg_top[0][0] if bg_top and bg_top[0][0] else ()
        if mode == "repo":
            main_cell = render_repo_cell(sig)
            bg_cell = render_repo_cell(bg_sig) if bg_sig else ""
            cell = main_cell + (f"<br><sub>existing board: {bg_cell}</sub>" if bg_sig else "")
        else:
            cell = render_vault_cell(sig, available_assets)
            if bg_sig:
                bg_html = render_vault_cell(bg_sig, available_assets)
                cell = (
                    cell + '<div style="opacity:.55;font-size:.85em;margin-top:4px">'
                    '<em>existing-board swings:</em><br>' + bg_html + '</div>'
                )
        L.append(f"| {n} | {w} | {wr2:.0f}% | {cell} |")
    L.append("")
    L.append("## Going 2nd")
    L.append("")
    if going_2nd_anom == 0:
        L.append(
            "**0 5-DON turns going 2nd.** Kalgara has no DON acceleration on "
            "its 2-4-6-8-10 curve, so a 5-DON turn going 2nd is structurally "
            "impossible. Confirmed zero anomalies after parser fix (player "
            "identity attribution: see `_other_with_leader` in `mantra/parser.py`)."
        )
    else:
        L.append(
            f"**{going_2nd_anom} anomalous rows.** Kalgara going 2nd cannot "
            f"reach 5 DON on the canonical 2-4-6-8-10 curve. These rows "
            f"indicate a parser regression — investigate `mantra/parser.py` "
            f"DON tracking or player attribution."
        )
    L.append("")
    L.append("## Card-level: what gets PLAYED on the 5-DON turn?")
    L.append("")
    L.append("Includes both hard-paid deploys (`deploy:`) and leader-effect plays from hand (`effect_deploy:` — Kalgara's post-attack reward).")
    L.append("")
    L.append("| Card id | Plays | Wins-when-played | WR | Source |")
    L.append("|---|---:|---:|---:|---|")
    for cid, n in deploys.most_common(20):
        w = deploy_wins[cid]
        wr3 = (w/n*100) if n else 0
        kinds = deploy_kind.get(cid, set())
        src = "hand+leader" if kinds == {"deploy","effect_deploy"} else next(iter(kinds))
        L.append(f"| `{cid}` | {n} | {w} | {wr3:.0f}% | {src} |")
    L.append("")
    L.append("## Card-level: what's DON-attached on the 5-DON turn?")
    L.append("")
    L.append("Covers both player-driven `attach_don` and effect-driven `effect_attach_don` (e.g. Nami, 5c Wyper).")
    L.append("")
    L.append("| Qty | Target | Times | Wins | WR |")
    L.append("|---:|---|---:|---:|---:|")
    for (qty,t), n in targets.most_common(20):
        w = target_wins[(qty,t)]
        wr4 = (w/n*100) if n else 0
        L.append(f"| {qty} | `{t}` | {n} | {w} | {wr4:.0f}% |")
    L.append("")
    L.append("## Caveats")
    L.append("")
    L.append("- **Top-MMR sample only.** OPBounty only uploads replays from top-200 / 3000+ bounty pilots. High-skill, not ladder average.")
    L.append("- **Standard queue (game_mode=0)** only. Other queue codes excluded.")
    L.append("- **Truncated logs** that didn't complete a 5-DON Kalgara turn are silently dropped. Truncation appears in newer-client logs that emit RZ1 state frames.")
    L.append("- **Action ordering** in the log reflects the in-game timeline, but some effect lines can land out of natural order (an effect may print AFTER the attack it modified). Treat the first-3 ordering as descriptive of opening intent, not strict sequence.")
    L.append("- **Going-2nd dropped.** Kalgara's DON curve going 2nd is 2-4-6-8-10 — there is no way to reach 5 DON on an even turn without an in-deck DON-accel card, which Kalgara doesn't run. Any 'going 2nd, 5 DON' row in the raw data is a parser miscount and has been excluded; see the Going 2nd section for the count.")
    return "\n".join(L)


# ---------- main ----------

def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.json")))
    parsed_all = []
    for f in files:
        try:
            parsed_all.append(json.load(open(f)))
        except Exception:
            pass
    print(f"Loaded {len(parsed_all)} parsed replays from {DIR}")

    have_winner = sum(1 for p in parsed_all if p.get("winner"))
    print(f"Winner attributed: {have_winner}/{len(parsed_all)}")

    kalgara_wins = 0
    kalgara_games = 0
    for p in parsed_all:
        for n, info in p.get("players", {}).items():
            if info.get("leader") == KALGARA:
                kalgara_games += 1
                if p.get("winner") == n:
                    kalgara_wins += 1
                break

    short_by_first = defaultdict(Counter)
    short_by_first_wins = defaultdict(Counter)
    short_samples = defaultdict(list)
    # For each main-sig, accumulate the background-sigs we saw alongside it
    # so we can display a representative background row underneath.
    bg_by_main: dict[tuple, Counter] = defaultdict(Counter)
    no_5don = 0
    for p in parsed_all:
        had_5don = False
        for won, first, main_sig, bg_sig, _turn in kalgara_5don_turns(p):
            had_5don = True
            shortsig = tuple(main_sig[:8])
            key = "1st" if first else "2nd"
            short_by_first[key][shortsig] += 1
            if won:
                short_by_first_wins[key][shortsig] += 1
            md = p.get("_metadata", {})
            if len(short_samples[shortsig]) < 3:
                short_samples[shortsig].append(md.get("path", "?"))
            bg_by_main[shortsig][tuple(bg_sig[:8])] += 1
        if not had_5don:
            no_5don += 1
    print(f"Going 1st 5-DON turns: {sum(short_by_first['1st'].values())}")
    print(f"Going 2nd anomalies dropped: {sum(short_by_first['2nd'].values())}")

    # Card-level rollups (1st only — 2nd is bogus)
    deploys = Counter()
    deploy_wins = Counter()
    deploy_kind: dict[str, set[str]] = {}
    targets = Counter()
    target_wins = Counter()
    for p in parsed_all:
        for won, first, main_sig, bg_sig, _turn in kalgara_5don_turns(p):
            if not first:
                continue
            for tok in main_sig:
                if tok.startswith("deploy:") or tok.startswith("effect_deploy:"):
                    kind, cid = tok.split(":",1)
                    deploys[cid] += 1
                    deploy_kind.setdefault(cid, set()).add(kind)
                    if won: deploy_wins[cid] += 1
                elif tok.startswith("attach_don:") or tok.startswith("effect_attach_don:"):
                    target = tok.split("->",1)[1]
                    qty = tok.split(":",1)[1].split("->",1)[0]
                    targets[(qty,target)] += 1
                    if won: target_wins[(qty,target)] += 1

    # Asset bootstrap — cards in the top-10 main sigs + their most-common
    # background sig (so the background row also renders thumbnails).
    top10_main_sigs = [s for s, _ in short_by_first["1st"].most_common(10)]
    top10_bg_sigs = [
        bg_by_main[s].most_common(1)[0][0] if bg_by_main[s] else ()
        for s in top10_main_sigs
    ]
    needed = collect_card_ids(top10_main_sigs + top10_bg_sigs)
    copied, downloaded, missing = ensure_assets(needed)
    print(f"Assets: {copied} copied locally, {downloaded} downloaded, {len(missing)} failed")
    available = set()
    for cid in needed:
        if os.path.exists(os.path.join(ASSETS_DIR_ABS, f"{cid}.png")):
            available.add(cid)

    # Mirror assets into the repo so GitHub can resolve the relative <img> paths.
    repo_assets_dir = os.path.join(REPO_DIR, "assets", "kalgara-vs-teach")
    os.makedirs(repo_assets_dir, exist_ok=True)
    for cid in available:
        src = os.path.join(ASSETS_DIR_ABS, f"{cid}.png")
        dst = os.path.join(repo_assets_dir, f"{cid}.png")
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)

    # Render repo report — vault-style HTML so GitHub shows thumbnails.
    common_kw = dict(
        parsed_all=parsed_all, kalgara_wins=kalgara_wins, kalgara_games=kalgara_games,
        no_5don=no_5don,
        short_by_first=short_by_first, short_by_first_wins=short_by_first_wins,
        short_samples=short_samples, bg_by_main=bg_by_main,
        deploys=deploys, deploy_wins=deploy_wins, deploy_kind=deploy_kind,
        targets=targets, target_wins=target_wins,
        mode="vault", available_assets=available,
    )
    repo_md = build_report(**common_kw)
    open(REPO_REPORT, "w").write(repo_md)
    print(f"Wrote repo report: {REPO_REPORT}")

    vault_md = build_report(**common_kw)
    os.makedirs(os.path.dirname(VAULT_REPORT), exist_ok=True)
    open(VAULT_REPORT, "w").write(vault_md)
    print(f"Wrote vault report: {VAULT_REPORT}")


if __name__ == "__main__":
    main()
