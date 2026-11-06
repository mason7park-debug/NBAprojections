# nba-data

Nightly NBA data snapshots for the `nba-projections` skill.

GitHub Actions runners have unrestricted network access to stats.nba.com.
Sandboxed agents usually don't. This repo bridges that gap: Actions fetches
the data and commits it, and the agent reads the committed CSVs over
`raw.githubusercontent.com`.

## Layout

```
.github/workflows/nba-data.yml   scheduled fetch (pregame + results)
scripts/fetch_nba_data.py        the fetcher
scripts/calibrate.py             margin SD and MAE-threshold calculations
scripts/minutes_by_margin.py     per-player minutes split by final margin
data/                            committed snapshots (written by Actions)
logs/                            projection logs, written before tip
```

## Schedule

| Cron (UTC) | ET | Mode | What |
|---|---|---|---|
| `37 22 * * *` | ~5:37pm | pregame | slate, tracking stats, baselines, game logs |
| `43 13 * * *` | ~8:43am | results | previous night's box scores |

GitHub's scheduler slips 5-20 minutes. The crons sit on off-minutes to reduce
it, but don't rely on exact timing. Run manually from the Actions tab any time
via **Run workflow**.

## Setup

1. Create the repo (see below) and push this folder.
2. Settings → Actions → General → Workflow permissions → **Read and write**.
   Without this the commit step fails.
3. Actions tab → NBA data snapshot → Run workflow → mode `pregame`.
4. Check that `data/` populated. If nba.com blocked the runner, you'll see
   retry failures in the log — fall back to running the scripts locally.

## Reading the data from an agent

```
https://raw.githubusercontent.com/<user>/nba-data/main/data/baseline/<date>.csv
```

Public repo required for unauthenticated reads.

## Open calibration questions

Two numbers in the skill are assumptions, not measurements:

- **Margin SD** (skill assumes 12). Needs to be SD of margin *around the
  closing spread*, not raw margin SD. Run
  `python scripts/calibrate.py --margin data/gamelogs/<season>.csv --spreads spreads.csv`.
- **MAE threshold vs baseline** (skill assumes 0.5). Run
  `python scripts/calibrate.py --threshold --log logs/rolling.csv` once a log
  exists. At 20 slates × 30 players the detection floor is ~0.46, so 0.5 is
  right at the edge of what's distinguishable from noise.
