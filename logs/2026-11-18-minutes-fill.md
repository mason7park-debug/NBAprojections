# Minutes fill replay, 2026-11-18

**Result: ON as "promote" with PROMOTE_POS "on" (model 2026-11-18).** Spreading the missing
minutes across the team did not help (first table below). Giving them to the player who takes
the open starting spot did, on both the live and the earlier nights.

## What works: the fill-in starter takes the minutes
Season box scores, 200 promotions (a player starting after starting under half of his last 5):
he gains about 7 minutes, more the less he usually plays (8 usual -> 22, 16 -> 23, 21 -> 28,
26 -> 30). Fit on the 148 before 11/12: **minutes = 17.7 + 0.44 x usual**. On the 52 live
promotions that cut his minutes miss from 9.1 to 5.9 when the right player is known.

The model has to guess who gets promoted. By most recent minutes it was right 52% of the time;
filling the open spot with a player at the missing starter's position first raised that to 58%
and stopped the wrong picks from costing floors.

| version | live PTS miss | live PTS floor | live vs line | earlier PTS miss | earlier PTS floor |
|---|---|---|---|---|---|
| off (2026-11-12b) | 5.246 | 82.7% | 47.9% | 5.003 | 80.4% |
| promote | 5.194 | 82.9% | 48.6% | 5.012 | 80.2% |
| promote + position (**on**) | 5.209 | 83.0% | 49.3% | 4.989 | 80.5% |
| promote+, K=0.3 | 5.194 | 82.7% | 47.5% | 5.018 | 80.0% |
| promote+, K=0.5 | 5.203 | 82.0% | 48.2% | 5.023 | 79.9% |

Minutes miss with the version that's on: live 5.00 -> 4.89, earlier 4.33 -> 4.33. The gains are small
overall because only about 5 players a night are fill-ins, but for them the points miss went from
7.4 to 6.4 on the live nights. Still well short of beating the prop lines.

## What did not work: spreading the minutes

## The problem (first look)
On the first 6 live nights (11/12 to 11/17) points ran +0.75 low and minutes ran +0.66 low.
When a player is ruled out, his minutes go to nobody: the fill-ins keep their usual minutes.
CLE on 11/14 (Mobley, Harden, Mitchell out): Proctor, Hezonja and Tyson were projected at
17 to 23 minutes and all played 34.

## What was tested (`NBA_MIN_FILL`, scripts/nightly.py)
| version | how | live PTS bias | live MIN bias | live PTS miss | live PTS floor | earlier PTS miss | earlier PTS floor |
|---|---|---|---|---|---|---|---|
| off (current) | | +0.74 | +0.66 | 5.246 | 82.7% | 5.003 | 80.4% |
| total | scale team up to 240 | +0.47 | +0.07 | 5.255 | 82.7% | 5.003 | 80.2% |
| even, K=0.6 | freed minutes shared by usual minutes | +0.05 | -0.83 | 5.288 | 81.6% | 5.031 | 79.8% |
| on, K=1.0 | freed minutes shared by room to grow | +0.01 | -1.05 | 5.280 | 81.1% | 5.031 | 79.6% |
| on, K=0.8 | | +0.13 | -0.79 | 5.258 | 82.0% | 5.025 | 79.7% |
| on, K=0.6 | | +0.26 | -0.48 | 5.239 | 81.8% | 5.019 | 79.7% |

Bias = actual minus projected. The versions that share out freed minutes fix the points
bias only by over-projecting minutes, so the fix is partly two errors cancelling.

Live = 11/12 to 11/17 (568 player-games). Earlier = 10/30 to 11/11 (1,377).
Lines: no version beat the prop lines (all 46 to 51%).

## Reading it
- The minutes miss is mostly spread, not level: fixing the average moved the typical miss
  very little (4.99 to 4.86 minutes at best).
- The bias shows up only on the live nights. The earlier nights ran slightly the other way
  (points -0.11, minutes -0.28), so a fix tuned to the live bias over-projects those.
- Late scratches matter: past-date injury files are the last snapshot of the day.

## Rerun at 15 live nights
```
for v in off promote; do
  cp -r . /tmp/rp/$v && cd /tmp/rp/$v
  for d in $(ls data/graded | sed 's/.csv//'); do
    NBA_MIN_FILL=$v python3 scripts/nightly.py project --date $d && python3 scripts/nightly.py grade --date $d
  done; cd -
done
python3 scripts/compare_replay.py /tmp/rp/off /tmp/rp/promote
```
