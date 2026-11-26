# Calibration check, 2026-11-23 (model 2026-11-19, no settings changed)

Checked on 11 live nights (11/12 to 11/22, 1,110 player-games per stat) and a full replay of every
graded night with the current settings.

## Fine as is
- **Floors** hit 85% (PTS), 89% (REB), 92% (AST), 93% (3PM) on the current model, above the 80% target.
  That is whole-number rounding, not caution: one notch higher they hit 79%, 72%, 70% and 55%.
  REB, AST and 3PM floors are as tight as whole numbers allow. Removing the REB/AST floor caps on the
  replay only moved them to 85% and 89%.
- **Threes "at least 1, 2, 3" chances** match what happened in every bucket (said 61%, made 64%;
  said 78%, made 76%; said 41%, made 45%).
- **Bias** is within half a point on every stat.

## Off, but not changed
- **Points ceilings** are reached 10.6% of the time against a 5% target, and still 6.3% two points
  higher. The simulation's upside for points is too narrow. Display only; a per-stat ceiling
  percentile (about 0.98 for points) would fix it.
- **Starter minutes by game script.** Non-star starters and stars played about 1.3 minutes more than
  projected in close games and 2.4 to 4 fewer in blowouts, because their season averages mix both.
  Tried lifting normal-game minutes for 24+ minute players (`NBA_CLOSE_MIN`): live-night minutes bias
  went from +0.36 to -0.09, but earlier nights got worse (-0.25 to -0.73) and accuracy did not move
  (points miss 5.081 to 5.083). Not kept.
- **Blowout tags** barely separate games: 78 live games, Low ended by 20+ 18%, Medium 22%, High 26%,
  with spreads of 8 to 12 ending by 20+ only 6% of the time. Too few games to refit SD; recheck at
  150 live games.

## Against the lines
3,233 graded lines: model over 60% right 50.7% (217), under 40% right 50.5% (730). Break-even at -110
is 52.4%. The line weight from 11/19 is doing its job (over chances now sit at 45 to 57%), so the
model by design rarely leans.

Backtest of the new lean rules on 11/13 to 11/22 (replayed, so not part of the live record):
| rule | W-L | win % |
|---|---|---|
| model vs line, 15%+ apart | 168-203 | 45% |
| hot streak in a good spot, over | 21-12 | 64% |
| fill-in starter, points over | 25-17 | 60% |
| star on a 10+ point underdog, points under | 9-9 | 50% |

Small samples. The live leans log (data/leans/) is the record to judge them on.
