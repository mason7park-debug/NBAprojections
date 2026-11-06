"""
Answers the two open questions in the nba-projections skill with data instead
of guesses:

  --margin   What is the real SD of final margin? (skill currently assumes 12)
  --threshold  What MAE gap vs baseline is actually detectable at a given
               sample size? (skill currently assumes 0.5)

Usage:
    python calibrate.py --margin data/gamelogs/2026-27.csv
    python calibrate.py --margin data/gamelogs/2026-27.csv --spreads spreads.csv
    python calibrate.py --threshold --slates 20 --players-per-slate 30
    python calibrate.py --threshold --log logs/rolling.csv
"""

import argparse
import math
import pandas as pd


# ---------------------------------------------------------------- margin SD

def margin_sd(gamelogs_csv, spreads_csv=None):
    """
    Raw margin SD is NOT the number the skill needs. The skill needs the SD of
    margin *around the spread* -- the residual after the market's estimate.
    Raw SD runs higher because it includes real differences in team strength
    that the spread already captures.

    Without spreads, this prints raw SD as an upper bound only.
    """
    df = pd.read_csv(gamelogs_csv)

    team_pts = df.groupby(["GAME_ID", "TEAM_ID"])["PTS"].sum().reset_index()
    total = team_pts.groupby("GAME_ID")["PTS"].transform("sum")
    team_pts["MARGIN"] = 2 * team_pts["PTS"] - total

    # One row per game (home side arbitrary; margin is symmetric).
    margins = team_pts.drop_duplicates("GAME_ID")["MARGIN"]
    print(f"games: {len(margins)}")
    print(f"RAW margin SD:        {margins.std():.2f}   <- upper bound, not the skill's number")

    if spreads_csv is None:
        print("\nNo spreads supplied. To get the number the skill actually needs,")
        print("pass --spreads with a CSV of GAME_ID,CLOSING_SPREAD (your Odds API")
        print("historical backfill can produce this). Residual SD is typically")
        print("meaningfully below raw SD; use the measured value, not an assumption.")
        return

    sp = pd.read_csv(spreads_csv)
    merged = team_pts.merge(sp, on="GAME_ID", how="inner")
    if merged.empty:
        print("No GAME_ID overlap between gamelogs and spreads.")
        return

    merged["RESIDUAL"] = merged["MARGIN"] - merged["CLOSING_SPREAD"]
    resid = merged["RESIDUAL"]
    print(f"\nmatched games: {len(merged)}")
    print(f"RESIDUAL margin SD:   {resid.std():.2f}   <- use this in the skill")
    print(f"residual mean:        {resid.mean():+.2f}   (should be near 0; "
          f"a large value means the spreads are misaligned)")

    sd = resid.std()
    print("\nImplied blowout probabilities with measured SD:")
    for spread in (1.5, 5, 8, 10):
        for thr in (13, 20):
            z = (thr - spread) / sd
            p = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))
            print(f"  fav by {spread:>4}: P(win by {thr}+) = {p * 100:4.1f}%")


# ------------------------------------------------------------- MAE threshold

def threshold(slates=None, players_per_slate=None, log_csv=None, sd_diff=None):
    """
    The 0.5 threshold in the skill is arbitrary. The defensible version asks:
    given the sample, what MAE gap can you even distinguish from noise?

    Model and baseline are graded on the SAME player-games, so this is a paired
    comparison. The relevant quantity is the SD of the per-player DIFFERENCE in
    absolute error, which is much smaller than the SD of either error alone.
    """
    if log_csv:
        df = pd.read_csv(log_csv)
        need = {"actual_PTS", "proj_PTS", "base_PTS"}
        if not need.issubset(df.columns):
            raise SystemExit(f"log needs columns {need}")
        d = (df["proj_PTS"] - df["actual_PTS"]).abs() - \
            (df["base_PTS"] - df["actual_PTS"]).abs()
        n, sd_diff = len(d), d.std()
        print(f"measured from log: n={n}, SD of paired AE difference = {sd_diff:.2f}")
        print(f"observed mean difference = {d.mean():+.3f} "
              f"(negative means the model beats baseline)")
        se = sd_diff / math.sqrt(n)
        print(f"standard error = {se:.3f}")
        print(f"95% CI on the difference: {d.mean() - 1.96 * se:+.3f} to {d.mean() + 1.96 * se:+.3f}")
        if d.mean() + 1.96 * se > 0:
            print("\n-> CI includes zero. The model is NOT yet shown to beat baseline.")
        return

    sd_diff = sd_diff or 4.0  # placeholder until a real log exists
    n = slates * players_per_slate
    se = sd_diff / math.sqrt(n)
    mde = 2.8 * se  # ~80% power, alpha .05

    print(f"assumed SD of paired AE difference: {sd_diff}  (REPLACE with measured)")
    print(f"n = {slates} slates x {players_per_slate} players = {n} player-games")
    print(f"standard error of the MAE difference: {se:.3f}")
    print(f"minimum detectable difference:        {mde:.2f} points of MAE")
    print()
    if mde > 0.5:
        print(f"-> A 0.5 threshold is BELOW what this sample can detect ({mde:.2f}).")
        print(f"   Either raise the threshold to ~{mde:.1f}, or collect "
              f"{int((2.8 * sd_diff / 0.5) ** 2)} player-games "
              f"({int((2.8 * sd_diff / 0.5) ** 2 / players_per_slate)} slates) "
              f"before judging at 0.5.")
    else:
        print(f"-> 0.5 is detectable at this sample ({mde:.2f} is the floor).")
        print("   Remaining question is whether 0.5 points of MAE is worth anything")
        print("   to you in practice. That part is a judgment call, not a statistic.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", metavar="GAMELOGS_CSV")
    ap.add_argument("--spreads", metavar="SPREADS_CSV")
    ap.add_argument("--threshold", action="store_true")
    ap.add_argument("--slates", type=int, default=20)
    ap.add_argument("--players-per-slate", type=int, default=30)
    ap.add_argument("--sd-diff", type=float)
    ap.add_argument("--log", metavar="ROLLING_CSV")
    a = ap.parse_args()

    if a.margin:
        margin_sd(a.margin, a.spreads)
    if a.threshold:
        print()
        threshold(a.slates, a.players_per_slate, a.log, a.sd_diff)
    if not a.margin and not a.threshold:
        ap.print_help()


if __name__ == "__main__":
    main()
