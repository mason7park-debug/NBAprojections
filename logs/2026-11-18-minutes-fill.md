# Minutes fill replay, 2026-11-18

**Result: left OFF.** No version lowered the points miss, and the ones that hand out
minutes cost the floors 1 to 2 points. Every version did worse on the earlier nights.

## The problem
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
for v in off total on; do
  cp -r . /tmp/rp/$v && cd /tmp/rp/$v
  for d in $(ls data/graded | sed 's/.csv//'); do
    NBA_MIN_FILL=$v python3 scripts/nightly.py project --date $d && python3 scripts/nightly.py grade --date $d
  done; cd -
done
python3 scripts/compare_replay.py /tmp/rp/off /tmp/rp/on
```
