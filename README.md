# NBA nightly projections

Runs by itself on GitHub Actions and publishes a results page with GitHub Pages.

- **Page:** the `docs/` folder, served by GitHub Pages (Settings, Pages, branch `main`, folder `/docs`).
- **Run it by hand:** Actions tab, "NBA nightly projections", Run workflow.
- **Schedule (US Eastern):** projections at about 11:31am, 2:31pm, 5:37pm and 6:27pm. Grading at about 8:43am the next day. A game that has tipped keeps the numbers from the last run before tip.

## How it works

1. `scripts/fetch_espn.py` saves the slate, odds, injuries and box scores from ESPN into `data/`.
2. `scripts/nightly.py project` builds everything from those files: player projections, blowout risk, simulated floors, target games and game predictions. It writes `data/projections/`, `data/gamepreds/` and `docs/data/latest.json`.
3. `scripts/nightly.py grade` compares the last slate with the final box scores and updates the all-nights record in `docs/data/grade.json`.
4. `scripts/fetch_props.py` is optional. With an `ODDS_API_KEY` secret it adds prop lines. It has not been run with a real key yet.

The model's settings are fixed constants at the top of `scripts/nightly.py`. Grading reports how they are doing and never changes them. Change them by hand, in one commit, when the record says so.

## Frozen settings and the live record

The settings were frozen on 2026-11-12 (`MODEL_VERSION` in `scripts/nightly.py`). One change was made after that, the same night, at the owner's request: last season's numbers as a starting point (version `2026-11-12b`, data in `data/prior/`). The record on the page is split in two: nights from Oct 30 to Nov 11 were replayed or projected late, and nights from Nov 12 on are live, projected before tip by the scheduled runs. Judge the model on the live nights. No setting changes until 15 live nights are graded, and a change then has to hold up on the live record as well as the replay.

Nothing here is betting advice. Floors and win chances are estimates from small samples.

## Layout

```
.github/workflows/nba-data.yml   scheduled fetch (pregame + results)
scripts/fetch_espn.py            THE FETCHER -- ESPN, works from Actions
scripts/calibrate.py             margin SD and MAE-threshold calculations
scripts/minutes_by_margin.py     per-player minutes split by final margin
scripts/fetch_nba_data.py        nba.com fetcher (blocked; kept for retry)
scripts/run_and_push.sh          local runner (unused; kept for retry)
scripts/com.mason.nbadata.plist  launchd schedule for the local runner
data/                            committed snapshots (written by Actions)
logs/                            projection logs, written before tip
```

## Data source: ESPN

`scripts/fetch_espn.py` pulls from ESPN's public endpoints. No API key, no
auth, standard library only.

**Why not stats.nba.com.** It blackholes datacenter IPs (requests time out
rather than erroring), so GitHub Actions failed on all five endpoints
2026-11-06. It was *also* unreachable from a residential connection the same
evening, so the local-runner fallback failed too. ESPN works from cloud
runners, so the fetch runs on Actions.

`scripts/fetch_nba_data.py` (nba.com) and `scripts/run_and_push.sh` +
`com.mason.nbadata.plist` (local runner) are kept for manual retry. If nba.com
becomes reachable again it restores the tracking stats ESPN lacks.

### What ESPN provides

| Need | Available | Notes |
|---|---|---|
| Season baselines | yes | 400 players, per-game and totals |
| Box scores | yes | incl. OREB/DREB split, DNP flag |
| Volume drivers | yes | FGA, 3PA, FTA, FGM, TO |
| Slate + schedule | yes | |
| Injury reports | yes | per game, with status and type |
| Spread + total | yes | DraftKings, same call as the box score |
| Rebound chances | **no** | nba.com tracking only |
| Potential assists | **no** | nba.com tracking only |

Injuries and odds arrive in the same per-game `summary` call as the box score,
so three sources collapse into one and the Odds API is not needed for spreads.

The two missing tracking fields degrade the projection model: REB falls back
to minutes x rebound rate, and AST loses its volume term entirely. See the
skill for how that changes the approach.

### Gotcha: duplicate labels

ESPN returns per-game and season-total values under the *same* short label,
and the order differs by category (in `general`, REB total comes BEFORE REB
per-game; in `offensive`, per-game comes first). Only `displayNames`
distinguishes them. Selecting on `labels` alone silently yields season totals
as per-game averages — this produced "Luka Doncic, 65 rebounds per game"
before it was fixed. Totals are preserved with a `_total` suffix.

## Schedule

GitHub Actions, twice daily:

| Cron (UTC) | ET | Mode | What |
|---|---|---|---|
| `43 13 * * *` | ~8:43am | results | previous night's box scores |
| `37 22 * * *` | ~5:37pm | pregame | slate, odds, injuries, baselines |

GitHub's scheduler slips 5-20 minutes. Run manually any time from the Actions
tab via **Run workflow**.

Exit codes: `0` clean, `1` partial fetch, `2` nothing fetched at all.

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
