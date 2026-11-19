# Calibration fixes, 2026-11-19 (model 2026-11-19)

Replayed against model 2026-11-18 on every graded night (10/30 to 11/18); prop lines exist from 11/13.

## Why
- **Prop lines.** Players went over about half the time wherever the book set the line against their
  recent games (line 25%+ above the last-5 average: 50% over, model said 35%). The line beat the model
  as a projection: points off by 5.05 vs 5.28 (last-5 average 5.66). The model's over chance carried no
  information beyond the line: it said 24% to 75%, players went over 49% to 52% every time.
- **Ceilings** at the 90th percentile were reached 16 to 26% of the time (meant to be 10%).
- **Floors** set close to the expected value (steady players) were missed about 1 time in 4.
- **Home edge.** Home teams won by 1.0 on average; the model had them at 2.1 (market 0.8).

## What changed
| setting | was | now |
|---|---|---|
| `NBA_LINE_W` (model weight where a line exists) | 1.0 | 0.25 |
| `NBA_P_OVER_CAL` (over chance shrunk to a quarter of its lean) | off | on |
| `NBA_CEIL_Q` | 0.90 | 0.95 |
| `NBA_FLOOR_CAP_PTS / REB / AST` (floor at most this x expected) | none | 0.65 / 0.70 / 0.70 |
| `NBA_HOME_EDGE` | 2.5 | 1.5 |

## Replay, nights with lines (11/13 to 11/18)
| | PTS | REB | AST | 3PM |
|---|---|---|---|---|
| miss, players with a line | 5.253 -> 5.041 | 2.094 -> 2.047 | 1.621 -> 1.606 | 1.195 -> 1.175 |
| floor hit | 82.5% -> 85.1% | 83.5% -> 85.4% | 88.9% -> 92.7% | 93.1% -> 93.1% |
| blowout floor hit | 88.2% -> 88.2% | 88.2% -> 90.1% | 90.7% -> 94.4% | 93.2% -> 93.2% |
| ceiling reached | 17.5% -> 10.1% | 17.2% -> 9.9% | 20.1% -> 12.7% | 28.1% -> 16.9% |
| over chance avg (actual) | 0.45 -> 0.50 (0.50) | 0.44 -> 0.49 (0.48) | 0.46 -> 0.50 (0.51) | 0.45 -> 0.50 (0.51) |

Side picks against the line stay about 50%: none of this creates an edge, it makes the numbers honest.
Games: margin miss 11.94 -> 11.85 (market 11.43), home bias -0.96 -> +0.04. Stronger team-rating
shrinkage (`NBA_RATE_K` 20) changed nothing.

## Caveats
Every setting was chosen on these same nights. The line weight held on a split (fit on 11/13 to 11/16,
tested on 11/17 to 11/18: 0.25 was best on both). Lower floors are less useful as targets in exchange
for being safer. Recheck at 15 live nights.

## Also checked, not changed
- **Foul trouble.** Fouls rise with minutes (more minutes, more chances to foul); only fouling out cut
  minutes, in 1.5% of games. A player's 5+ foul games did not repeat (split-half correlation 0.06), and
  facing a team that draws free throws did not change fouls. ESPN's feed has no referees before tip.
- **Game model vs market.** Its disagreements with the spread carried no information (weight -0.10 in
  a regression with the market), and its injury adjustments did not help (12.94 vs 12.93 margin miss
  with and without). It over-rated teams it liked: CHA +2.3 vs the market, then 10.7 worse than the model.
