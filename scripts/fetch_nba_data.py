"""
Nightly NBA data snapshot for the nba-projections skill.

Runs on GitHub Actions (which has unrestricted network) and commits CSVs that
a sandboxed agent can later read over raw.githubusercontent.com.

  --mode pregame   slate, player tracking inputs, season baselines
  --mode results   final box scores for the previous day

Install:  pip install nba_api pandas
"""

import argparse
import datetime as dt
import pathlib
import sys
import time

import pandas as pd
from nba_api.stats.endpoints import (
    leaguedashptstats,
    leaguedashplayerstats,
    playergamelogs,
    scoreboardv2,
    boxscoretraditionalv2,
)

# nba.com rate-limits aggressively and rejects default user agents.
PAUSE = 1.2

# NOTE: stats.nba.com blackholes cloud-provider IP ranges (GitHub Actions, EC2,
# etc). Requests time out rather than returning an error status. Run this from a
# residential connection. Confirmed failing from GitHub runners 2026-11-06.

FAILED = []   # labels that never came back
WROTE = []    # labels actually written


def retry(fn, label, attempts=4):
    for i in range(attempts):
        try:
            out = fn()
            time.sleep(PAUSE)
            return out
        except Exception as exc:
            wait = 2 ** i
            print(f"  [{label}] attempt {i + 1} failed ({exc}); retrying in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
    print(f"  [{label}] GIVING UP after {attempts} attempts", file=sys.stderr)
    FAILED.append(label)
    return None


def write(df, path, label):
    if df is None or len(df) == 0:
        print(f"  skip {label}: no data")
        if label not in FAILED:
            FAILED.append(label)
        return
    WROTE.append(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  wrote {path}  ({len(df)} rows)")


def season_string(today):
    """NBA season spans two years; Oct-Jun belongs to the season starting that Oct."""
    y = today.year if today.month >= 10 else today.year - 1
    return f"{y}-{str(y + 1)[-2:]}"


def pregame(out, today, season):
    print("mode=pregame")

    sb = retry(lambda: scoreboardv2.ScoreboardV2(
        game_date=today.strftime("%Y-%m-%d")).get_data_frames()[0], "scoreboard")
    write(sb, out / "slate" / f"{today}.csv", "slate")

    # Tracking inputs. These are the fields the projection decomposition needs.
    for measure, name in [("Rebounding", "rebounding"), ("Passing", "passing")]:
        df = retry(lambda m=measure: leaguedashptstats.LeagueDashPtStats(
            season=season, player_or_team="Player",
            pt_measure_type=m, per_mode_simple="PerGame"
        ).get_data_frames()[0], f"pt_{name}")
        write(df, out / "tracking" / f"{name}_{today}.csv", name)

    # Season baselines -- this is what the model has to beat.
    base = retry(lambda: leaguedashplayerstats.LeagueDashPlayerStats(
        season=season, per_mode_detailed="PerGame").get_data_frames()[0], "baseline")
    write(base, out / "baseline" / f"{today}.csv", "baseline")

    # Full game logs: feeds the minutes-by-margin table and the margin SD.
    logs = retry(lambda: playergamelogs.PlayerGameLogs(
        season_nullable=season).get_data_frames()[0], "gamelogs")
    write(logs, out / "gamelogs" / f"{season}.csv", "gamelogs")


def results(out, today, season):
    print("mode=results")
    yday = today - dt.timedelta(days=1)

    sb = retry(lambda: scoreboardv2.ScoreboardV2(
        game_date=yday.strftime("%Y-%m-%d")).get_data_frames()[0], "scoreboard")
    if sb is None or len(sb) == 0:
        print("  no games found for", yday)
        return

    frames = []
    for gid in sb["GAME_ID"].unique():
        bs = retry(lambda g=gid: boxscoretraditionalv2.BoxScoreTraditionalV2(
            game_id=g).get_data_frames()[0], f"box_{gid}")
        if bs is not None:
            frames.append(bs)

    if frames:
        write(pd.concat(frames, ignore_index=True),
              out / "boxscores" / f"{yday}.csv", "boxscores")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pregame", "results"], required=True)
    ap.add_argument("--out", default="data")
    ap.add_argument("--allow-partial", action="store_true",
                    help="exit 0 if at least one fetch succeeded (default: any "
                         "failure is an error)")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    today = dt.date.today()
    season = season_string(today)
    print(f"season={season} date={today}")

    (pregame if args.mode == "pregame" else results)(out, today, season)

    # A nightly job that fails silently is worse than no job. Exit non-zero so
    # the scheduler, the shell wrapper and the user all find out.
    print(f"\nwrote: {WROTE or 'nothing'}")
    if FAILED:
        print(f"FAILED: {FAILED}", file=sys.stderr)
        if not WROTE:
            print("Nothing was fetched at all. If every request timed out, this "
                  "machine's IP is likely blocked by stats.nba.com -- run from a "
                  "residential connection.", file=sys.stderr)
            sys.exit(2)
        if not args.allow_partial:
            sys.exit(1)
        print("continuing anyway (--allow-partial)", file=sys.stderr)
    else:
        print("all fetches succeeded")


if __name__ == "__main__":
    main()
