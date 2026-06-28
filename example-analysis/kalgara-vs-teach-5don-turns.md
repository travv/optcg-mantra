# Kalgara vs by Teach — 5-DON Turn Analysis

**Date:** 2026-06-28
**Source:** OPBounty replay collection — standard queue (game_mode=0), top-200 ladder or 3000+ bounty pilots only.
**Replays loaded:** 246
**With at least one Kalgara 5-DON turn:** 130
**Kalgara win rate in this sample:** 134/244 = 54.9%

**Method:** For each replay, find Kalgara's turn whose `don_at_start == 5` (the first 5-DON turn, i.e. turn 3 going 2nd or turn 4 going 1st). Take the action sequence on that turn — `deploy`, `attach_don`, `attack` (vs leader/body), `counter`, `effect:source_card`. Group by the first 5 meaningful actions ('short signature'). Snapshot lines and combat-resolve lines are dropped — they're bookkeeping, not decisions.

Note: card-id readability is left to the reader; e.g. `OP15-114` = 5c Wyper, `OP08-098` = Kalgara leader, `OP08-099` = 4c New Kalgara, `OP06-111` = Braham, `OP05-106` = Shura, `OP05-117` = Counter (Earth Won't Lose), `EB03-053` = Zeus.

## Top 5-DON action openings (first 5 meaningful tokens)

| Freq | Wins | WR | Tokens | Sample replays |
|---:|---:|---:|---|---|
| 21 | 11 | 52% | `deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER · effect:OP08-098` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_1763_3211_2026-06-15T16:33:08.log<br>Replays/2026-W24/0/OP16-080/OP08-098_2866_4667_2026-06-17T11:38:00.log<br>Replays/2026-W24/0/OP16-080/OP08-098_2163_2825_2026-06-18T05:02:55.log</sub> |
| 15 | 5 | 33% | `deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_3318_2087_2026-06-15T14:55:41.log<br>Replays/2026-W24/0/OP16-080/OP08-098_3269_4370_2026-06-16T07:07:10.log<br>Replays/2026-W24/0/OP16-080/OP08-098_1891_1673_2026-06-16T10:47:43.log</sub> |
| 4 | 2 | 50% | `attack:LEADER · effect:OP16-080 · effect:OP16-080 · effect:OP16-103 · effect:OP16-103` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_1861_3018_2026-06-15T07:32:41.log<br>Replays/2026-W24/0/OP08-098/OP16-080_934_1630_2026-06-17T15:11:12.log<br>Replays/2026-W24/0/OP16-080/OP08-098_2204_2296_2026-06-18T06:26:32.log</sub> |
| 4 | 1 | 25% | `deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114 · attack:LEADER` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_1293_2013_2026-06-16T23:07:42.log<br>Replays/2026-W24/0/OP16-080/OP08-098_1513_2255_2026-06-18T22:40:48.log<br>Replays/2026-W25/0/OP16-080/OP08-098_1738_2165.log</sub> |
| 4 | 2 | 50% | `attack:LEADER · deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114` | <sub>Replays/2026-W25/0/OP16-080/OP08-098_3945_5093.log<br>Replays/2026-W25/0/OP16-080/OP08-098_1275_1292.log<br>Replays/2026-W25/0/OP08-098/OP16-080_1636_2299.log</sub> |
| 3 | 1 | 33% | `attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098 · effect:OP08-098 · effect:OP12-099` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_4268_4012_2026-06-18T05:07:02.log<br>Replays/2026-W25/0/OP16-080/OP08-098_2339_2307.log<br>Replays/2026-W25/0/OP16-080/OP08-098_2051_2526.log</sub> |
| 3 | 2 | 67% | `attack:LEADER · counter:OP09-086(1000) · deploy:EB03-053 · effect:EB03-053 · effect:EB03-053` | <sub>Replays/2026-W25/0/OP16-080/OP08-098_1737_2678.log<br>Replays/2026-W25/0/OP08-098/OP16-080_4986_3130.log<br>Replays/2026-W25/0/OP08-098/OP16-080_1078_1534.log</sub> |
| 3 | 2 | 67% | `attack:LEADER · counter:OP09-086(1000) · deploy:OP15-114 · effect:OP15-114 · effect:OP15-114` | <sub>Replays/2026-W25/0/OP16-080/OP08-098_3786_2161.log<br>Replays/2026-W25/0/OP08-098/OP16-080_3053_1892.log<br>Replays/2026-W25/0/OP08-098/OP16-080_1921_1860.log</sub> |
| 3 | 1 | 33% | `attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098 · effect:OP08-098 · effect:OP16-080` | <sub>Replays/2026-W25/0/OP08-098/OP16-080_2137_1669.log<br>Replays/2026-W25/0/OP16-080/OP08-098_3680_2322.log<br>Replays/2026-W26/0/OP16-080/OP08-098_2055_1243.log</sub> |
| 3 | 1 | 33% | `deploy:OP15-101 · effect:OP15-101 · effect:OP15-101 · effect:OP15-101 · effect:None` | <sub>Replays/2026-W25/0/OP08-098/OP16-080_2343_1604.log<br>Replays/2026-W25/0/OP16-080/OP08-098_1184_1346.log<br>Replays/2026-W25/0/OP16-080/OP08-098_2322_1708.log</sub> |
| 2 | 1 | 50% | `attack:LEADER · deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_2249_3059_2026-06-14T21:48:25.log<br>Replays/2026-W26/0/OP16-080/OP08-098_2526_2162.log</sub> |
| 2 | 2 | 100% | `deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER · effect:OP16-080` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_4839_3074_2026-06-17T04:15:02.log<br>Replays/2026-W25/0/OP08-098/OP16-080_1173_782.log</sub> |
| 2 | 2 | 100% | `attack:LEADER · counter:OP16-109(2000) · deploy:EB03-053 · effect:EB03-053 · effect:EB03-053` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_4871_2457_2026-06-17T08:49:47.log<br>Replays/2026-W25/0/OP08-098/OP16-080_1661_1170.log</sub> |
| 2 | 0 | 0% | `attack:LEADER · counter:OP16-106(1000) · deploy:OP15-114 · effect:OP15-114 · effect:OP15-114` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_2332_2522.log<br>Replays/2026-W25/0/OP16-080/OP08-098_2344_1578.log</sub> |
| 2 | 2 | 100% | `deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER · counter:OP09-095(1000)` | <sub>Replays/2026-W25/0/OP08-098/OP16-080_1745_1766.log<br>Replays/2026-W25/0/OP08-098/OP16-080_2833_1876.log</sub> |
| 2 | 0 | 0% | `deploy:OP15-114 · effect:OP15-114 · attack:LEADER · effect:OP08-098 · effect:OP08-098` | <sub>Replays/2026-W25/0/OP16-080/OP08-098_2655_2060.log<br>Replays/2026-W25/0/OP16-080/OP08-098_1881_1722.log</sub> |
| 2 | 2 | 100% | `attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098 · effect:OP08-098 · effect:OP06-114` | <sub>Replays/2026-W25/0/OP08-098/OP16-080_2428_1800.log<br>Replays/2026-W25/0/OP08-098/OP16-080_2831_2898.log</sub> |
| 1 | 1 | 100% | `attack:LEADER · counter:OP16-103(1000) · attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098` | <sub>Replays/2026-W24/0/OP08-098/OP16-080_2936_2099_2026-06-15T15:36:35.log</sub> |
| 1 | 0 | 0% | `attack:LEADER · effect:OP16-108 · effect:OP16-108 · deploy:OP15-119` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_1874_1274_2026-06-15T21:46:21.log</sub> |
| 1 | 0 | 0% | `attack:BODY · deploy:OP15-101 · effect:OP15-101 · effect:OP15-101 · effect:OP15-101` | <sub>Replays/2026-W24/0/OP16-080/OP08-098_3266_2700_2026-06-16T04:39:25.log</sub> |

## 1st vs 2nd split (top 10 each)

### Going **1st**  (125 5-DON turns)

| Freq | Wins | WR | Tokens |
|---:|---:|---:|---|
| 21 | 11 | 52% | `deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER · effect:OP08-098` |
| 15 | 5 | 33% | `deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114` |
| 4 | 2 | 50% | `attack:LEADER · deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114` |
| 3 | 2 | 67% | `attack:LEADER · effect:OP16-080 · effect:OP16-080 · effect:OP16-103 · effect:OP16-103` |
| 3 | 1 | 33% | `attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098 · effect:OP08-098 · effect:OP12-099` |
| 3 | 1 | 33% | `deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114 · attack:LEADER` |
| 3 | 2 | 67% | `attack:LEADER · counter:OP09-086(1000) · deploy:EB03-053 · effect:EB03-053 · effect:EB03-053` |
| 3 | 1 | 33% | `attach_don:1->OP08-098 · attack:LEADER · effect:OP08-098 · effect:OP08-098 · effect:OP16-080` |
| 3 | 1 | 33% | `deploy:OP15-101 · effect:OP15-101 · effect:OP15-101 · effect:OP15-101 · effect:None` |
| 2 | 1 | 50% | `attack:LEADER · deploy:EB03-053 · effect:EB03-053 · effect:EB03-053 · attack:LEADER` |

### Going **2nd**  (5 5-DON turns)

| Freq | Wins | WR | Tokens |
|---:|---:|---:|---|
| 1 | 0 | 0% | `deploy:OP15-114 · effect:OP15-114 · effect:OP15-114 · effect:OP15-114 · attack:LEADER` |
| 1 | 0 | 0% | `attack:LEADER · effect:OP16-080 · effect:OP16-080 · effect:OP16-103 · effect:OP16-103` |
| 1 | 0 | 0% | `deploy:OP15-108 · effect:OP15-108 · effect:None · attach_don:2->OP08-098 · attack:LEADER` |
| 1 | 0 | 0% | `attack:LEADER · counter:OP09-086(1000) · deploy:OP15-114 · effect:OP15-114 · effect:OP15-114` |
| 1 | 1 | 100% | `attack:LEADER · effect:OP16-109 · effect:OP16-109 · effect:OP16-109 · deploy:OP15-114` |

## Card-level: what gets PLAYED on the 5-DON turn?

| Card id | Plays | Wins-when-played | WR |
|---|---:|---:|---:|
| `OP15-114` | 48 | 19 | 40% |
| `EB03-053` | 45 | 26 | 58% |
| `OP15-101` | 12 | 5 | 42% |
| `OP08-110` | 5 | 3 | 60% |
| `OP15-108` | 4 | 0 | 0% |
| `OP05-117` | 3 | 0 | 0% |
| `OP15-111` | 3 | 1 | 33% |
| `OP15-113` | 3 | 2 | 67% |
| `OP15-119` | 2 | 1 | 50% |
| `OP11-106` | 2 | 0 | 0% |
| `OP15-110` | 2 | 0 | 0% |
| `OP05-106` | 1 | 0 | 0% |
| `OP06-102` | 1 | 0 | 0% |

## Card-level: what's DON-attached on the 5-DON turn?

| Qty | Target | Times | Wins | WR |
|---:|---|---:|---:|---:|
| 1 | `OP08-098` | 28 | 11 | 39% |
| 2 | `OP08-098` | 6 | 1 | 17% |
| 1 | `OP15-101` | 2 | 1 | 50% |
| 2 | `OP15-101` | 1 | 0 | 0% |
| 3 | `OP08-098` | 1 | 0 | 0% |
| 5 | `OP08-098` | 1 | 0 | 0% |

## Caveats

- **Top-MMR sample only.** OPBounty only uploads replays from top-200 / 3000+ bounty pilots. This is high-skill play, not ladder average.
- **Standard queue (game_mode=0)** only. Other queue codes excluded.
- **Truncated logs** that didn't complete a 5-DON Kalgara turn are silently dropped. Truncation appears in newer-client logs that emit RZ1 state frames and may end mid-game.
- **Action ordering** in the log reflects the in-game action timeline, but it's possible for some effect lines to land out of natural order (e.g. an effect prints AFTER the attack it modified). Treat the first-3 ordering as descriptive of opening intent, not strict sequence.
- **`don_at_start == 5`** picks Kalgara's turn 4 going 1st OR turn 3 going 2nd — but it can also pick a later turn if Kalgara was DON-returned. Filtering to first-occurrence-per-replay would be cleaner; current code reports all 5-DON turns. (For Kalgara most games only have one 5-DON turn since there's no return-DON effect in the deck.)