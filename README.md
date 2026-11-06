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

## Why the fetch runs locally

GitHub Actions **cannot** fetch this data. stats.nba.com blackholes
cloud-provider IP ranges: requests time out rather than returning an error
status. Verified 2026-11-06, all five endpoints failed 4/4 attempts from a
GitHub runner. cdn.nba.com is reachable from cloud hosts and serves schedule
and box scores, but not the tracking stats (rebound chances, potential
assists) this project depends on.

So the fetch runs on a residential connection and pushes here. The repo is
storage: a persistent log that a sandboxed agent can read over
raw.githubusercontent.com without the Mac being awake.

## Schedule

`scripts/com.mason.nbadata.plist` runs `run_and_push.sh auto` twice daily:

| Local time | Mode (chosen by hour) | What |
|---|---|---|
| 08:45 | results | previous night's box scores |
| 17:40 | pregame | slate, tracking stats, baselines, game logs |

launchd skips runs while the Mac is asleep and does not make them up. A missed
evening is a missed slate, not a broken pipeline.

## Setup

1. `chmod +x scripts/run_and_push.sh`
2. Test once by hand: `./scripts/run_and_push.sh pregame`
3. Edit `REPO_PATH` in `scripts/com.mason.nbadata.plist` to this folder's path.
4. `cp scripts/com.mason.nbadata.plist ~/Library/LaunchAgents/`
5. `launchctl load ~/Library/LaunchAgents/com.mason.nbadata.plist`

Check status with `launchctl list | grep nbadata` (second column is the last
exit code) and `tail ~/.../logs/run/*.log`.

Exit codes from `run_and_push.sh`: `0` clean, `1` partial fetch or push
failure, `2` nothing fetched at all (usually a blocked IP).

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
