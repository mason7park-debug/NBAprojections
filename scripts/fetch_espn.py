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
    rows, offset, page = [], 0, 100
    while True:
        url = (f"{WEB}/statistics/byathlete?region=us&lang=en&season={season}"
               f"&seasontype=2&limit={page}&offset={offset}")
        d = get(url, f"baselines[{offset}]")
        if not d:
            break
        athletes = d.get("athletes", [])
        if not athletes:
            break

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

        total = d.get("pagination", {}).get("count", 0)
        offset += page
        if offset >= total:
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

def fetch_summaries(game_ids, date, out, want_box):
    """
    One call per game returns box score, injuries and betting lines together.
    """
    box_rows, inj_rows, odds_rows = [], [], []

    for gid in game_ids:
        d = get(f"{SITE}/summary?event={gid}", f"summary[{gid}]")
        if not d:
            continue

        # --- betting lines
        for o in (d.get("pickcenter") or d.get("odds") or [])[:1]:
            odds_rows.append({
                "game_id": gid,
                "provider": (o.get("provider") or {}).get("name"),
                "spread": o.get("spread"),
                "over_under": o.get("overUnder"),
                "details": o.get("details"),
            })

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
                        for lab, val in zip(labels, a.get("stats", [])):
                            row[lab.replace("+/-", "plusminus")] = val
                        box_rows.append(row)

    write_csv(odds_rows, out / "odds" / f"{date}.csv", "odds")
    write_csv(inj_rows, out / "injuries" / f"{date}.csv", "injuries")
    if want_box:
        write_csv(box_rows, out / "boxscores" / f"{date}.csv", "boxscores")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pregame", "results"], required=True)
    ap.add_argument("--out", default="data")
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    today = dt.date.today()
    print(f"date={today} season={season_year(today)}")

    (pregame if args.mode == "pregame" else results)(out, today)

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
