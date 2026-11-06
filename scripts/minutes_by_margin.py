"""
Build a per-player minutes-by-final-margin table from NBA game logs.

Replaces guessed "34 competitive / 28 lopsided" numbers with each player's own
empirical minutes split by how lopsided the game actually was.

Requires network access to stats.nba.com -- run this on your own machine, not
in a sandbox. Install with:  pip install nba_api pandas

Usage:
    python minutes_by_margin.py --season 2026-27 --out minutes_by_margin.csv
"""

import argparse
import time
import pandas as pd
from nba_api.stats.endpoints import playergamelogs

# Final-margin buckets. Edit these if you want a different split.
# There is no accepted league-wide "garbage time" threshold, so these are a
# choice, not a standard. Keep them fixed once you start logging or the
# record stops being comparable.
BUCKETS = [(0, 5, "tight"), (6, 10, "clear"), (11, 15, "comfortable"), (16, 999, "lopsided")]


def bucket(margin):
    m = abs(margin)
    for lo, hi, name in BUCKETS:
        if lo <= m <= hi:
            return name
    return "lopsided"


def fetch(season, season_type="Regular Season", retries=3):
    for attempt in range(retries):
        try:
            return playergamelogs.PlayerGameLogs(
                season_nullable=season, season_type_nullable=season_type
            ).get_data_frames()[0]
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} after error: {exc}")
            time.sleep(2 ** attempt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True, help='e.g. "2026-27"')
    ap.add_argument("--out", default="minutes_by_margin.csv")
    ap.add_argument("--min-games", type=int, default=3,
                    help="drop player/bucket cells with fewer games than this")
    args = ap.parse_args()

    print(f"Fetching game logs for {args.season} ...")
    df = fetch(args.season)
    print(f"  {len(df)} player-games")

    # PLUS_MINUS is the player's on-court margin, not the game's. Derive the
    # game margin from team score vs opponent score where available; fall back
    # to WL sign times the team's point differential for that game.
    if {"PTS", "TEAM_ID", "GAME_ID"}.issubset(df.columns):
        team_pts = df.groupby(["GAME_ID", "TEAM_ID"])["PTS"].sum().reset_index()
        game_tot = team_pts.groupby("GAME_ID")["PTS"].transform("sum")
        team_pts["MARGIN"] = 2 * team_pts["PTS"] - game_tot
        df = df.merge(team_pts[["GAME_ID", "TEAM_ID", "MARGIN"]],
                      on=["GAME_ID", "TEAM_ID"], how="left")
    else:
        raise SystemExit("Expected PTS/TEAM_ID/GAME_ID columns; check nba_api version.")

    df["BUCKET"] = df["MARGIN"].apply(bucket)

    out = (df.groupby(["PLAYER_ID", "PLAYER_NAME", "BUCKET"])
             .agg(games=("MIN", "size"), avg_min=("MIN", "mean"), sd_min=("MIN", "std"))
             .reset_index())
    out = out[out["games"] >= args.min_games]
    out["avg_min"] = out["avg_min"].round(1)
    out["sd_min"] = out["sd_min"].round(1)

    wide = out.pivot_table(index=["PLAYER_ID", "PLAYER_NAME"],
                           columns="BUCKET", values="avg_min").reset_index()
    wide.to_csv(args.out, index=False)
    print(f"Wrote {args.out}  ({len(wide)} players)")

    # League-wide shape: how much do minutes actually move with margin?
    league = out.groupby("BUCKET").apply(
        lambda g: (g["avg_min"] * g["games"]).sum() / g["games"].sum()
    )
    print("\nLeague average minutes by final margin:")
    for _, _, name in BUCKETS:
        if name in league.index:
            print(f"  {name:12} {league[name]:.1f}")
    print("\nIf the spread between tight and lopsided is under ~2 minutes for")
    print("most players, the game-script adjustment is not worth its complexity.")


if __name__ == "__main__":
    main()
