"""
One-time: last season's player totals and team scoring, saved under data/prior/.
Used as a starting point early in the season, when this season's sample is small.

    python scripts/fetch_prior.py --season 2026      # ESPN calls the 2025-26 season "2026"
"""
import argparse, csv, json, pathlib, urllib.request

ATH = ("https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete"
       "?region=us&lang=en&contentorigin=espn&isqualified=false&limit=100&seasontype=2&season={s}&page={p}")
STAND = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?seasontype=2&season={s}"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--out", default="data/prior")
    a = ap.parse_args()
    label = f"{a.season - 1}-{str(a.season)[2:]}"
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows, page, pages, names = [], 1, 1, None
    while page <= pages:
        d = get(ATH.format(s=a.season, p=page))
        pages = d["pagination"]["pages"]
        names = names or {c["name"]: c["names"] for c in d["categories"]}
        for x in d["athletes"]:
            v = {}
            for c in x["categories"]:
                v.update({f"{c['name']}.{n}": t for n, t in zip(names[c["name"]], c.get("totals", []))})
            try:
                rows.append([x["athlete"]["id"], x["athlete"]["displayName"], int(float(v["general.gamesPlayed"])),
                             int(float(v["general.minutes"])), int(float(v["offensive.points"])),
                             int(float(v["general.rebounds"])), int(float(v["offensive.assists"])),
                             int(float(v["offensive.threePointFieldGoalsMade"]))])
            except (KeyError, ValueError):
                pass
        page += 1
    with (out / f"players_{label}.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["player_id", "player", "gp", "minutes", "pts", "reb", "ast", "tpm"])
        w.writerows(r for r in rows if r[2] > 0 and r[3] > 0)
    s = get(STAND.format(s=a.season))
    with (out / f"teams_{label}.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["team", "pts_for", "pts_against"])
        for conf in s["children"]:
            for e in conf["standings"]["entries"]:
                st = {x["name"]: x.get("value") for x in e["stats"]}
                w.writerow([e["team"]["abbreviation"], round(st["avgPointsFor"], 2), round(st["avgPointsAgainst"], 2)])
    print(f"saved {len(rows)} players and team scoring for {label}")


if __name__ == "__main__":
    main()
