"""
Build NBA player projections for a slate and write a pre-tip log.

    python scripts/project.py --date 2026-11-07 --data data --out logs

Reads the pregame snapshot (slate, odds, injuries, baseline) that
fetch_espn.py committed, and writes logs/<date>.md before first tip.
grade.py scores that file against box scores the next morning.

METHOD (v4). Per-minute season rates scaled by projected minutes, then
adjusted for pace, implied team score and injury redistribution. No tracking
stats: ESPN does not expose rebound chances or potential assists, so the
volume x rate decomposition is only partially available.

MINUTES is the binding constraint. On 2026-11-06, minutes MAE was 4.83 with a
+1.63 bias, and the four stats all landed within noise of a season-average
baseline. Holding minutes to their realized values would have cut points MAE
from 5.18 to 4.04, so the rate model was fine and minutes ate the gain.
"""

import argparse, csv, json, math, pathlib, datetime as dt

# --- Minutes multipliers by |final margin|, as a ratio of a straight
# --- minutes-average projection. Fit on ONE slate (2026-11-06, 74 starter
# --- and 74 bench lines). PROVISIONAL STARTING VALUES, NOT A CALIBRATION.
#
# Starters are monotonic and plausible. Bench is noisy -- the 13-20 band is 17
# players and 1.25 is probably overfit. Both tables are RAW ratios, not
# normalized to the close-game band: bench was overprojected ~15% even in close
# games, and normalizing hides that level error (doing so made minutes bias
# WORSE, +1.63 -> +2.11).
#
# Ceiling: role x final margin explains only 16% of minutes-error variance.
# Even knowing the exact final margin caps points MAE near 4.95 vs 4.04 for
# true per-player minutes. The remaining 84% is rotation, foul trouble and
# matchup -- a different and much harder problem than this table.
#
# REFIT at ~20 logged slates, on held-out days. Everything below is in-sample.
STARTER_MULT = [(0, 7, 0.999), (8, 12, 0.996), (13, 20, 0.924), (21, 99, 0.843)]
BENCH_MULT   = [(0, 7, 0.848), (8, 12, 0.928), (13, 20, 1.253), (21, 99, 0.978)]

MARGIN_SD = 12.0      # assumption, not measured; see scripts/calibrate.py
STARTER_MIN = 28      # minutes threshold separating the two tables
LEAGUE_TOTAL = 228.0  # for pace scaling
ROSTER_N = 10
MAX_MIN = 37.0


def p_band(spread, lo, hi):
    """P(|final margin| in [lo,hi]) with margin ~ N(spread, MARGIN_SD)."""
    c = lambda x: 0.5 * (1 + math.erf((x - spread) / (MARGIN_SD * math.sqrt(2))))
    return (c(hi) - c(lo)) + (c(-lo) - c(-hi))


def minutes_mult(spread, is_starter):
    """Expectation of the multiplier over the margin distribution.

    Deliberately NOT a blowout flag: which games blow out is unpredictable.
    At -1.5 a 13+ win still happens ~17% of the time; at -8, ~34%. Integrating
    puts that uncertainty in the point estimate instead of pretending to know.
    """
    table = STARTER_MULT if is_starter else BENCH_MULT
    z = sum(p_band(spread, lo, hi) for lo, hi, _ in table)
    if z <= 0:
        return 1.0
    return sum(p_band(spread, lo, hi) * m for lo, hi, m in table) / z


def load(data, date):
    d = pathlib.Path(data)
    def rd(sub):
        p = d / sub / f"{date}.csv"
        if not p.exists():
            raise SystemExit(f"missing {p} -- run fetch_espn.py --mode pregame first")
        return list(csv.DictReader(p.open()))
    base = {}
    for r in rd("baseline"):
        def f(k):
            try: return float(r[k])
            except: return 0.0
        if f("MIN") > 6:
            base.setdefault(r["team"], []).append(
                {"p": r["player"], "min": f("MIN"), "PTS": f("PTS"),
                 "REB": f("REB"), "AST": f("AST"), "3PM": f("3PM")})
    out = {(r["team"], r["player"]) for r in rd("injuries")
           if r["status"].lower() in ("out", "doubtful")}
    odds = {r["game_id"]: r for r in rd("odds")}
    slate = {r["game_id"]: r for r in rd("slate")}
    return base, out, odds, slate


def project_team(team, base, out, spread, total):
    """spread: positive = this team favored by that many."""
    team_score = total / 2 + spread / 2
    pace = total / LEAGUE_TOTAL

    roster = [x for x in base.get(team, []) if (team, x["p"]) not in out]
    roster.sort(key=lambda x: -x["min"])
    roster = roster[:ROSTER_N]
    if not roster:
        return [], team_score

    # Redistribute minutes freed by ruled-out players, weighted by existing
    # minutes, capped so a thin roster doesn't inflate everyone.
    avail = sum(x["min"] for x in roster)
    spread_scale = min(240.0 / avail, 1.25) if avail else 1.0

    pts_base = sum(x["PTS"] for x in roster)
    score_adj = max(0.88, min(1.15, team_score / pts_base)) if pts_base else 1.0

    rows = []
    for x in roster:
        starter = x["min"] >= STARTER_MIN
        m = min(x["min"] * spread_scale, MAX_MIN) * minutes_mult(abs(spread), starter)
        sc = m / x["min"] if x["min"] else 1.0
        rows.append({
            "p": x["p"], "MIN": m,
            "PTS": x["PTS"] * sc * score_adj,
            "REB": x["REB"] * sc * pace,
            "AST": x["AST"] * sc * score_adj,
            "3PM": x["3PM"] * sc * pace,
            # the naive baseline this must beat -- logged alongside, always
            "base_PTS": x["PTS"], "base_REB": x["REB"],
            "base_AST": x["AST"], "base_3PM": x["3PM"],
        })
    return rows, team_score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(dt.date.today()))
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="logs")
    a = ap.parse_args()

    base, out, odds, slate = load(a.data, a.date)
    now = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)  # ET

    L = [f"# Projections {a.date}",
         f"Method: v4 (margin-integrated minutes) | Generated {now:%H:%M} ET",
         "Source: ESPN | Baseline: season per-game average, logged per player",
         "Minutes multipliers are provisional values fit on one slate (2026-11-06),",
         "evaluated in-sample. Refit at ~20 slates on held-out days.", ""]

    for gid, s in slate.items():
        o = odds.get(gid, {})
        total = float(o.get("over_under") or LEAGUE_TOTAL)
        det = (o.get("details") or "").split()
        fav, line = (det[0], abs(float(det[1]))) if len(det) == 2 else (None, 0.0)
        L.append(f"\n## {s['away']} @ {s['home']}   {o.get('details','')}   O/U {total}")
        for team in (s["away"], s["home"]):
            sp = line if team == fav else -line
            rows, ts = project_team(team, base, out, sp, total)
            if not rows:
                L.append(f"\n### {team} — no eligible players"); continue
            L.append(f"\n### {team} (implied {ts:.0f})")
            L.append("| Player | MIN | PTS | REB | AST | 3PM |")
            L.append("|---|---|---|---|---|---|")
            for r in rows:
                L.append(f"| {r['p']} | {r['MIN']:.0f} | {r['PTS']:.1f} | "
                         f"{r['REB']:.1f} | {r['AST']:.1f} | {r['3PM']:.1f} |")

    p = pathlib.Path(a.out) / f"{a.date}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
