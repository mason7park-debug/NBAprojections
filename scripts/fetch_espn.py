"""
Nightly NBA data snapshot via ESPN's public endpoints.

Why ESPN and not stats.nba.com: nba.com blackholes datacenter IPs AND, as of
2026-11-06, was unreachable from a residential connection too. ESPN works from
cloud runners, so this can run on GitHub Actions.

What ESPN gives us that nba.com needed three sources for: box scores, injury
reports and betting lines all come from the same per-game summary endpoint.

What ESPN does NOT give us: tracking stats (rebound chances, potential
assists). The projection model's volume x rate decomposition is degraded
without them -- see the skill's notes on REB and AST.

  --mode pregame   slate, odds, injuries, season baselines
  --mode results   final box scores for the previous day
  --mode backfill  box scores for every date from --start to yesterday
                   (one-time, or to repair gaps)

Results and backfill also write data/teamstats/<date>.csv: one row per team
per game with threes, free throws, points in the paint, rebounds, assists,
steals, blocks and turnovers, plus the opponent and final margin. The model
derives area defense and pace from those rows.

No API key. No auth. Undocumented public endpoints, so they can change without
notice -- that is the tradeoff for them being reachable at all.
"""

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

PAUSE = 0.4
UA = "nba-projections/1.0 (personal research project)"

FAILED = []
WROTE = []
SB_ODDS = {}   # game_id -> odds row seen on the scoreboard (fallback)


def get(url, label, attempts=4):
    """Fetch JSON with backoff. Returns None after exhausting attempts."""
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            time.sleep(PAUSE)
            return data
        except Exception as exc:
            wait = 2 ** i
            print(f"  [{label}] attempt {i+1} failed ({exc}); retrying in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
    print(f"  [{label}] GIVING UP after {attempts} attempts", file=sys.stderr)
    FAILED.append(label)
    return None


def write_json(obj, path, label):
    if not obj:
        print(f"  skip {label}: no data")
        if label not in FAILED:
            FAILED.append(label)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1))
    n = len(obj) if isinstance(obj, list) else 1
    print(f"  wrote {path}  ({n} records)")
    WROTE.append(label)


def write_csv(rows, path, label):
    if not rows:
        print(f"  skip {label}: no rows")
        if label not in FAILED:
            FAILED.append(label)
        return
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path}  ({len(rows)} rows)")
    WROTE.append(label)


def espn_date(d):
    return d.strftime("%Y%m%d")


def season_year(today):
    """ESPN labels a season by its ending year: 2026-27 -> 2027."""
    return today.year + 1 if today.month >= 10 else today.year


# ------------------------------------------------------------------ baselines

def fetch_baselines(season, out, today):
    """Season per-game averages. This is the naive baseline the model must beat."""
    # ESPN paginates with `page`, NOT `offset`. Passing offset returns page 1
    # every time -- which silently yielded 100 unique players repeated 4x.
    rows, page_no, per_page, seen = [], 1, 100, set()
    while True:
        url = (f"{WEB}/statistics/byathlete?region=us&lang=en&season={season}"
               f"&seasontype=2&limit={per_page}&page={page_no}")
        d = get(url, f"baselines[p{page_no}]")
        if not d:
            break
        athletes = d.get("athletes", [])
        if not athletes:
            break
        # Guard against the failure returning: if a page repeats what we have,
        # stop rather than writing duplicates.
        page_ids = {a.get("athlete", {}).get("id") for a in athletes}
        if page_ids and page_ids <= seen:
            print(f"  [baselines] page {page_no} repeated earlier ids; stopping",
                  file=sys.stderr)
            break
        seen |= page_ids

        # Label lists live at the top level, one per category, parallel to each
        # athlete's value arrays. CAREFUL: labels repeat -- ESPN returns both
        # per-game and season-total values under the same short label, and the
        # order differs by category (in "general", REB total comes BEFORE REB
        # per-game; in "offensive", per-game comes first). Only displayNames
        # distinguishes them, so select on that and ignore `labels` for the
        # ambiguous ones.
        labels = {c["name"]: c.get("labels", []) for c in d.get("categories", [])}
        display = {c["name"]: c.get("displayNames", []) for c in d.get("categories", [])}

        for a in athletes:
            ath = a.get("athlete", {})
            row = {
                "player_id": ath.get("id"),
                "player": ath.get("displayName"),
                "team": (ath.get("teamShortName") or
                         (ath.get("team") or {}).get("abbreviation")),
                "position": (ath.get("position") or {}).get("abbreviation"),
            }
            for cat in a.get("categories", []):
                cname = cat["name"]
                names = labels.get(cname, [])
                disp = display.get(cname, [])
                vals = cat.get("values", [])
                for i, (lab, val) in enumerate(zip(names, vals)):
                    key = lab.replace("%", "pct").replace("+/-", "plusminus")
                    dn = disp[i] if i < len(disp) else ""
                    is_total = not ("Per Game" in dn or "Average" in dn
                                    or "Percentage" in dn)
                    if is_total:
                        # Keep totals under a _total suffix so nothing is lost
                        # and nothing silently overwrites a per-game value.
                        row.setdefault(f"{key}_total", val)
                    else:
                        row[key] = val
            # GP is a count, not an average, so it lands in the totals bucket.
            # Alias it back: downstream code needs games played by name.
            if "GP" not in row and "GP_total" in row:
                row["GP"] = row["GP_total"]
            rows.append(row)

        pages = d.get("pagination", {}).get("pages", 1)
        page_no += 1
        if page_no > pages:
            break

    write_csv(rows, out / "baseline" / f"{today}.csv", "baselines")
    return rows


# ---------------------------------------------------------------------- slate

def fetch_scoreboard(date, out, label):
    d = get(f"{SITE}/scoreboard?dates={espn_date(date)}", f"scoreboard[{date}]")
    if not d:
        return []
    events = d.get("events", [])
    rows = []
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        for o in (comp.get("odds") or [])[:1]:
            SB_ODDS[e.get("id")] = {
                "game_id": e.get("id"),
                "provider": (o.get("provider") or {}).get("name"),
                "spread": o.get("spread"),
                "over_under": o.get("overUnder"),
                "details": o.get("details"),
            }
        rows.append({
            "game_id": e.get("id"),
            "date": e.get("date"),
            "name": e.get("shortName"),
            "status": (e.get("status") or {}).get("type", {}).get("name"),
            "home": (teams.get("home", {}).get("team") or {}).get("abbreviation"),
            "away": (teams.get("away", {}).get("team") or {}).get("abbreviation"),
            "home_score": teams.get("home", {}).get("score"),
            "away_score": teams.get("away", {}).get("score"),
        })
    write_csv(rows, out / "slate" / f"{date}.csv", label)
    return [r["game_id"] for r in rows if r["game_id"]]


# ------------------------------------------------------- per-game summary data

BOX_LABELS = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL",
              "BLK", "OREB", "DREB", "PF", "plusminus"]


def _made_att(v):
    try:
        m, a = str(v).split("-")
        return int(m), int(a)
    except Exception:
        return None, None


def _num(v):
    try:
        return int(float(v))
    except Exception:
        return None


def team_stat_rows(d, gid):
    """One row per team for a finished game: totals, opponent, final margin."""
    score, home = {}, {}
    comps = ((d.get("header") or {}).get("competitions") or [{}])[0]
    for c in comps.get("competitors", []):
        ab = (c.get("team") or {}).get("abbreviation")
        score[ab] = _num(c.get("score"))
        home[ab] = c.get("homeAway") == "home"
    rows = []
    for t in (d.get("boxscore") or {}).get("teams", []):
        ab = (t.get("team") or {}).get("abbreviation")
        st = {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
        fgm, fga = _made_att(st.get("fieldGoalsMade-fieldGoalsAttempted"))
        tpm, tpa = _made_att(st.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
        ftm, fta = _made_att(st.get("freeThrowsMade-freeThrowsAttempted"))
        opp = next((k for k in score if k != ab), None)
        pts, opp_pts = score.get(ab), score.get(opp)
        rows.append({
            "game_id": gid, "team": ab, "opp": opp, "home": home.get(ab),
            "PTS": pts, "OPP_PTS": opp_pts,
            "margin": (pts - opp_pts) if pts is not None and opp_pts is not None else None,
            "FGM": fgm, "FGA": fga, "3PM": tpm, "3PA": tpa, "FTM": ftm, "FTA": fta,
            "REB": _num(st.get("totalRebounds")), "OREB": _num(st.get("offensiveRebounds")),
            "AST": _num(st.get("assists")), "STL": _num(st.get("steals")),
            "BLK": _num(st.get("blocks")),
            "TOV": _num(st.get("totalTurnovers") or st.get("turnovers")),
            "PAINT": _num(st.get("pointsInPaint")),
        })
    return rows


def fetch_summaries(game_ids, date, out, want_box):
    """
    One call per game returns box score, injuries and betting lines together.
    """
    box_rows, inj_rows, odds_rows, team_rows = [], [], [], []

    for gid in game_ids:
        d = get(f"{SITE}/summary?event={gid}", f"summary[{gid}]")
        if not d:
            continue

        # --- betting lines (summary first, scoreboard as fallback)
        got_line = False
        for o in (d.get("pickcenter") or d.get("odds") or [])[:1]:
            if o.get("spread") is None and o.get("overUnder") is None:
                continue
            got_line = True
            odds_rows.append({
                "game_id": gid,
                "provider": (o.get("provider") or {}).get("name"),
                "spread": o.get("spread"),
                "over_under": o.get("overUnder"),
                "details": o.get("details"),
            })
        if not got_line and gid in SB_ODDS:
            odds_rows.append(SB_ODDS[gid])

        # --- injuries
        for t in d.get("injuries", []):
            team = (t.get("team") or {}).get("abbreviation")
            for p in t.get("injuries", []):
                ath = p.get("athlete", {})
                inj_rows.append({
                    "game_id": gid,
                    "team": team,
                    "player_id": ath.get("id"),
                    "player": ath.get("displayName"),
                    "status": p.get("status"),
                    "type": (p.get("details") or {}).get("type"),
                })

        # --- box score
        if want_box:
            for team_blk in (d.get("boxscore") or {}).get("players", []):
                team = (team_blk.get("team") or {}).get("abbreviation")
                for stat_blk in team_blk.get("statistics", []):
                    labels = stat_blk.get("labels", [])
                    for a in stat_blk.get("athletes", []):
                        ath = a.get("athlete", {})
                        row = {"game_id": gid, "team": team,
                               "player_id": ath.get("id"),
                               "player": ath.get("displayName"),
                               "dnp": a.get("didNotPlay", False)}
                        # Every row carries every column, so DNP rows (which
                        # have no stats) cannot shift the CSV header.
                        for lab in BOX_LABELS:
                            row[lab] = ""
                        for lab, val in zip(labels, a.get("stats", [])):
                            row[lab.replace("+/-", "plusminus")] = val
                        row["starter"] = a.get("starter", False)
                        row["pos"] = (ath.get("position") or {}).get("abbreviation")
                        box_rows.append(row)
            team_rows.extend(team_stat_rows(d, gid))

    # Odds and injuries are point-in-time. A pregame run always writes them.
    # A post-game run must not replace the pregame snapshot with what the feed
    # says the morning after, so it only fills files that do not exist yet.
    for rows, kind in ((odds_rows, "odds"), (inj_rows, "injuries")):
        path = out / kind / f"{date}.csv"
        if want_box and path.exists():
            print(f"  keep {path} (pregame snapshot)")
            continue
        write_csv(rows, path, kind)
    if want_box:
        write_csv(box_rows, out / "boxscores" / f"{date}.csv", "boxscores")
        write_csv(team_rows, out / "teamstats" / f"{date}.csv", "teamstats")


# ----------------------------------------------------------------------- main

def pregame(out, today):
    print("mode=pregame")
    gids = fetch_scoreboard(today, out, "slate")
    print(f"  {len(gids)} games on the slate")
    if gids:
        fetch_summaries(gids, today, out, want_box=False)
    fetch_baselines(season_year(today), out, today)


def results(out, today):
    print("mode=results")
    yday = today - dt.timedelta(days=1)
    gids = fetch_scoreboard(yday, out, "slate_yesterday")
    print(f"  {len(gids)} games to grade")
    if gids:
        fetch_summaries(gids, yday, out, want_box=True)
    # Repair pass: if an earlier results run failed, its date has a slate but
    # no box score. Refill up to 5 such dates so the history has no holes.
    fixed = 0
    for p in sorted((out / "slate").glob("*.csv"), reverse=True):
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d >= yday or (out / "boxscores" / f"{d}.csv").exists():
            continue
        fill_date(out, d)
        fixed += 1
        if fixed >= 5:
            break


def fill_date(out, d):
    """Box scores and team stats for one past date. No games is not an error."""
    data = get(f"{SITE}/scoreboard?dates={espn_date(d)}", f"scoreboard[{d}]")
    if not data:
        return
    if not data.get("events"):
        print(f"  {d}: no games")
        return
    before = list(FAILED)
    gids = fetch_scoreboard(d, out, f"slate[{d}]")
    done = [g for g in gids]
    if done:
        fetch_summaries(done, d, out, want_box=True)
    # injuries and odds are point-in-time; for a past date they are optional
    for lab in ("odds", "injuries"):
        if lab in FAILED and lab not in before:
            FAILED.remove(lab)


def backfill(out, today, start):
    print(f"mode=backfill from {start}")
    d = start
    while d < today:
        if (out / "boxscores" / f"{d}.csv").exists() and (out / "teamstats" / f"{d}.csv").exists():
            print(f"  {d}: already have it")
        else:
            fill_date(out, d)
        d += dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pregame", "results", "backfill"], required=True)
    ap.add_argument("--out", default="data")
    ap.add_argument("--date", help="run as if today were this date (YYYY-MM-DD)")
    ap.add_argument("--start", help="backfill: first date to fetch (YYYY-MM-DD)")
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    # The schedule runs on UTC machines, but a "day" of NBA games is a US
    # Eastern day. At 01:00 UTC it is still the previous evening in the US.
    today = (dt.date.fromisoformat(args.date) if args.date
             else (dt.datetime.utcnow() - dt.timedelta(hours=5)).date())
    print(f"date={today} season={season_year(today)}")

    if args.mode == "pregame":
        pregame(out, today)
    elif args.mode == "results":
        results(out, today)
    else:
        if not args.start:
            ap.error("--mode backfill needs --start YYYY-MM-DD")
        backfill(out, today, dt.date.fromisoformat(args.start))

    print(f"\nwrote: {WROTE or 'nothing'}")
    if FAILED:
        print(f"FAILED: {FAILED}", file=sys.stderr)
        if not WROTE:
            print("Nothing fetched at all. ESPN may be down or the endpoints "
                  "may have changed shape.", file=sys.stderr)
            sys.exit(2)
        if not args.allow_partial:
            sys.exit(1)
        print("continuing anyway (--allow-partial)", file=sys.stderr)
    else:
        print("all fetches succeeded")


if __name__ == "__main__":
    main()
