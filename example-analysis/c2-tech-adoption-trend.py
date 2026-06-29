#!/usr/bin/env python3
"""C2 — tech adoption time series, per leader.

For one chosen leader, aggregates decklists from the OPBounty corpus
(week by week) and surfaces:

  * Weekly inclusion rate per card (% of decks running ≥1 copy).
  * Weekly conditional win rate (win rate when card present vs overall).
  * Biggest movers (latest week vs prior).
  * New entrants and departures.

Filters to "flex slots" (5%-95% inclusion) so always-4-of staples don't
drown the signal. Cells with fewer than `MIN_SAMPLE_PER_WEEK` decks are
flagged inline as small-sample.

Usage:
    MANTRA_VAULT_ROOT=~/vault/replays \\
        python3 c2-tech-adoption-trend.py OP08-098 \\
            --out-dir ./tech-trends

Output: `<out-dir>/<leader>-<YYYY-MM-DD>.md`.
"""
import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mantra.analyzer.decklist import leader_decklist_for
from mantra.analyzer.matchup_lookup import vault_root
from mantra.analyzer.replay_loader import iter_matchup_folders, load_matchup_folder

MIN_SAMPLE_PER_WEEK = 10
FLEX_LOW = 0.05
FLEX_HIGH = 0.95


def collect_leader_decks(leader_id: str, root: str) -> tuple[list[dict], set[str]]:
    decks: list[dict] = []
    folders: set[str] = set()
    for a, b in iter_matchup_folders(root):
        if leader_id not in (a, b):
            continue
        folder = os.path.join(root, f"{a}-vs-{b}")
        folders.add(folder)
        for p in load_matchup_folder(folder):
            res = leader_decklist_for(p, leader_id)
            if not res:
                continue
            deck, won = res
            if not deck:
                continue
            md = p.get("_metadata", {})
            decks.append({
                "week": md.get("week", "unknown"),
                "won": won,
                "deck": deck,
            })
    return decks, folders


def aggregate_by_week(decks: list[dict]) -> tuple[
    list[str], dict[str, int], dict[str, dict[str, dict]], dict[str, int]
]:
    total_per_week: Counter = Counter()
    wins_per_week: Counter = Counter()
    cards: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"included": 0, "wins_with": 0})
    )
    for d in decks:
        w = d["week"]
        total_per_week[w] += 1
        if d["won"]:
            wins_per_week[w] += 1
        for cid in d["deck"]:
            cards[cid][w]["included"] += 1
            if d["won"]:
                cards[cid][w]["wins_with"] += 1
    weeks = sorted(total_per_week)
    return weeks, total_per_week, cards, wins_per_week


def inclusion_rate(included: int, total: int) -> float:
    return included / total if total else 0.0


def card_movers(cards, total_per_week, weeks) -> list[tuple[str, float, float, float]]:
    if len(weeks) < 2:
        return []
    latest, prior = weeks[-1], weeks[-2]
    out = []
    for cid, by_week in cards.items():
        l = inclusion_rate(by_week[latest]["included"], total_per_week[latest])
        p = inclusion_rate(by_week[prior]["included"], total_per_week[prior])
        if not (FLEX_LOW <= max(l, p) <= FLEX_HIGH):
            if max(l, p) > FLEX_HIGH:
                continue
            if max(l, p) < FLEX_LOW and abs(l - p) < FLEX_LOW:
                continue
        out.append((cid, l, p, l - p))
    out.sort(key=lambda r: abs(r[3]), reverse=True)
    return out


def new_entrants_and_departures(cards, total_per_week, weeks):
    if len(weeks) < 2:
        return [], []
    latest, prior = weeks[-1], weeks[-2]
    new = []
    gone = []
    for cid, by_week in cards.items():
        l = inclusion_rate(by_week[latest]["included"], total_per_week[latest])
        p = inclusion_rate(by_week[prior]["included"], total_per_week[prior])
        if p == 0 and l >= FLEX_LOW:
            new.append((cid, l))
        elif l == 0 and p >= FLEX_LOW:
            gone.append((cid, p))
    new.sort(key=lambda r: -r[1])
    gone.sort(key=lambda r: -r[1])
    return new, gone


def card_performance_gap(cards, total_per_week, wins_per_week, latest_week):
    if not total_per_week[latest_week]:
        return []
    overall = wins_per_week[latest_week] / total_per_week[latest_week]
    out = []
    for cid, by_week in cards.items():
        cell = by_week[latest_week]
        n = cell["included"]
        if n < 5:
            continue
        with_wr = cell["wins_with"] / n
        rate = inclusion_rate(n, total_per_week[latest_week])
        if rate > FLEX_HIGH:
            continue
        out.append((cid, with_wr, overall, with_wr - overall, n))
    out.sort(key=lambda r: abs(r[3]), reverse=True)
    return out


def fmt_pct(x: float) -> str:
    return f"{x*100:.0f}%"


def arrow(delta: float) -> str:
    if delta > 0.05: return "↑"
    if delta < -0.05: return "↓"
    return "→"


def build_report(leader_id: str, decks: list[dict], folders: set[str]) -> str:
    weeks, total_per_week, cards, wins_per_week = aggregate_by_week(decks)
    today = datetime.now().strftime("%Y-%m-%d")

    L: list[str] = []
    L.append(f"# {leader_id} — Tech adoption time series")
    L.append("")
    L.append(f"**Date:** {today}")
    L.append("**Source:** OPBounty replay collection — standard queue, top-200 ladder / 3000+ bounty pilots.")
    L.append(f"**Matchup folders walked:** {len(folders)}")
    L.append(f"**Decks indexed:** {len(decks)} (only replays with populated `winner_deck`/`loser_deck` count)")
    L.append("")

    if not decks:
        L.append("⚠️ No decks found for this leader. Snapshot more matchup data with `snapshot_replays` first.")
        return "\n".join(L) + "\n"

    L.append("## Sample by week")
    L.append("")
    L.append("| Week | Decks | Win rate (this leader) |")
    L.append("|---|---:|---:|")
    for w in weeks:
        wr = wins_per_week[w] / total_per_week[w] if total_per_week[w] else 0
        flag = " ⚠️ small sample" if total_per_week[w] < MIN_SAMPLE_PER_WEEK else ""
        L.append(f"| {w} | {total_per_week[w]} | {fmt_pct(wr)}{flag} |")
    L.append("")

    L.append("## Weekly inclusion rate (flex slots only — between 5% and 95%)")
    L.append("")
    L.append("Rows are cards that aren't always-in or always-out. Trend column shows the latest week vs prior.")
    L.append("")
    header_cols = "| Card | " + " | ".join(weeks) + " | Trend |"
    sep_cols = "|---" * (len(weeks) + 2) + "|"
    L.append(header_cols)
    L.append(sep_cols)

    flex_cards = []
    for cid, by_week in cards.items():
        rates = [inclusion_rate(by_week[w]["included"], total_per_week[w]) for w in weeks]
        max_rate = max(rates)
        if max_rate < FLEX_LOW or max_rate > FLEX_HIGH:
            continue
        flex_cards.append((cid, rates))
    flex_cards.sort(key=lambda r: -max(r[1]))

    for cid, rates in flex_cards[:30]:
        cells = " | ".join(fmt_pct(r) for r in rates)
        trend = arrow(rates[-1] - rates[-2]) if len(rates) >= 2 else "—"
        L.append(f"| `{cid}` | {cells} | {trend} |")
    if len(flex_cards) > 30:
        L.append(f"| _{len(flex_cards) - 30} more flex cards omitted_ |" + (" |" * (len(weeks) + 1)))
    L.append("")

    movers = card_movers(cards, total_per_week, weeks)
    L.append("## Biggest movers (latest week vs prior)")
    L.append("")
    if not movers:
        L.append("_Not enough weekly data to compute movers (need ≥2 weeks)._")
    elif len(weeks) >= 2 and (
        total_per_week[weeks[-1]] < MIN_SAMPLE_PER_WEEK
        or total_per_week[weeks[-2]] < MIN_SAMPLE_PER_WEEK
    ):
        L.append(f"⚠️ One of the compared weeks has <{MIN_SAMPLE_PER_WEEK} decks — movers may be noisy.")
        L.append("")
    if movers:
        L.append(f"Comparing **{weeks[-1]}** to **{weeks[-2]}**.")
        L.append("")
        L.append("| Card | Latest | Prior | Δ |")
        L.append("|---|---:|---:|---:|")
        for cid, latest, prior, delta in movers[:15]:
            sign = "+" if delta >= 0 else ""
            L.append(f"| `{cid}` | {fmt_pct(latest)} | {fmt_pct(prior)} | {sign}{delta*100:.1f}pp |")
    L.append("")

    new, gone = new_entrants_and_departures(cards, total_per_week, weeks)
    L.append("## New entrants this week")
    L.append("")
    if not new:
        L.append("_No new entrants ≥5% inclusion._")
    else:
        for cid, rate in new[:10]:
            L.append(f"- `{cid}` — {fmt_pct(rate)} of decks this week (was 0%)")
    L.append("")
    L.append("## Departures this week")
    L.append("")
    if not gone:
        L.append("_No departures from ≥5% inclusion._")
    else:
        for cid, rate in gone[:10]:
            L.append(f"- `{cid}` — was {fmt_pct(rate)} last week (now 0%)")
    L.append("")

    latest = weeks[-1] if weeks else None
    gap = card_performance_gap(cards, total_per_week, wins_per_week, latest) if latest else []
    L.append(f"## Performance gap — {latest}" if latest else "## Performance gap")
    L.append("")
    L.append("Cards whose presence in a list correlates with above/below the leader's overall win rate this week (sample ≥5).")
    L.append("")
    if not gap:
        L.append("_Not enough samples per card this week to compute gaps._")
    else:
        L.append("| Card | WR with card | Overall WR | Δ | n |")
        L.append("|---|---:|---:|---:|---:|")
        for cid, with_wr, overall, gap_val, n in gap[:15]:
            sign = "+" if gap_val >= 0 else ""
            L.append(
                f"| `{cid}` | {fmt_pct(with_wr)} | {fmt_pct(overall)} | "
                f"{sign}{gap_val*100:.1f}pp | {n} |"
            )
    L.append("")

    L.append("## Caveats")
    L.append("")
    L.append("- **Replay sample is biased to snapshotted matchups.** Folders walked: " + ", ".join(sorted(os.path.basename(f) for f in folders)) + ".")
    L.append("- **Not every replay has a populated decklist** — only replays where OPBounty captured `winner_deck`/`loser_deck` are counted.")
    L.append(f"- **Movers and performance gap need ≥{MIN_SAMPLE_PER_WEEK} decks per week to be reliable.** Small-sample weeks are flagged inline.")
    L.append("- **Performance gap is correlational, not causal** — a card may be included in winning lists without being the reason they win (e.g. tech that's only run by skilled pilots).")

    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("leader_id", help="Leader card id, e.g. OP08-098")
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)),
                    help="Output directory for the report markdown. "
                         "Defaults to the script's own directory.")
    args = ap.parse_args()

    root = vault_root()
    decks, folders = collect_leader_decks(args.leader_id, root)
    print(f"Collected {len(decks)} decks for {args.leader_id} across {len(folders)} matchup folders")
    report = build_report(args.leader_id, decks, folders)
    os.makedirs(args.out_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(args.out_dir, f"{args.leader_id}-{today}.md")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
