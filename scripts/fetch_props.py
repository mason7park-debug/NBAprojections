"""
Player prop lines for tonight, written to data/props/<date>.csv.

    python scripts/fetch_props.py --out data

Source 1 (no key needed): ESPN's public odds feed, which carries one sportsbook's player
lines (points, rebounds, assists, threes). Players are matched by ESPN player id, the same
id the box scores use, so there is no name matching.

Source 2 (optional): The Odds API, used only if the ODDS_API_KEY secret is set and ESPN
returned nothing. Its lines are matched by name. This path has never been run with a key.

Lines never feed the projection. They sit beside it as an outside check and are graded
each morning.

Only games that have not tipped are fetched, so a line is always a pregame line. Rows for
games that have already started are carried over from the earlier file.
"""
import argparse, csv, datetime as dt, json, os, pathlib, re, statistics, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{id}/competitions/{id}/odds"
ESPN_TYPES = {"Total Points": "PTS", "Total Rebounds": "REB", "Total Assists": "AST",
              "Total 3-Point Field Goals": "3PM"}
ODDS_API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
ODDS_API_STAT = {"player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST", "player_threes": "3PM"}
COLS = ["game_id", "player_id", "player", "stat", "line", "source"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def espn_game(gid):
    """All player lines ESPN lists for one game: {(player_id, stat): line}."""
    found = {}
    providers = get(CORE.format(id=gid) + "?limit=50").get("items", [])
    for prov in providers:
        pid = (prov.get("provider") or {}).get("id")
        if not pid or "propBets" not in prov:
            continue
        page, pages = 1, 1
        while page <= pages:
            d = get(CORE.format(id=gid) + f"/{pid}/propBets?limit=1000&page={page}")
            pages = d.get("pageCount") or 1
            for it in d.get("items", []):
                stat = ESPN_TYPES.get((it.get("type") or {}).get("name"))
                ref = (it.get("athlete") or {}).get("$ref", "")
                m = re.search(r"/athletes/(\d+)", ref)
                val = ((it.get("current") or {}).get("target") or {}).get("value")
                if stat and m and val is not None:
                    found.setdefault((m.group(1), stat), []).append(float(val))
            page += 1
        if found:
            return {k: statistics.median(v) for k, v in found.items()}, (prov.get("provider") or {}).get("name", "ESPN")
    return {}, None


def odds_api(date, key, names):
    markets = os.environ.get("PROP_MARKETS", "").strip() or "player_points"
    rows = []
    events = get(f"{ODDS_API}/events?apiKey={urllib.parse.quote(key)}")
    for ev in events:
        tip = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        if tip.astimezone(ET).date() != date or tip <= dt.datetime.now(dt.timezone.utc):
            continue
        d = get(f"{ODDS_API}/events/{ev['id']}/odds?apiKey={urllib.parse.quote(key)}"
                f"&regions=us&oddsFormat=american&markets={markets}")
        found = {}
        for book in d.get("bookmakers", []):
            for m in book.get("markets", []):
                stat = ODDS_API_STAT.get(m.get("key"))
                for o in m.get("outcomes", []) if stat else []:
                    if o.get("name") == "Over" and o.get("description") and o.get("point") is not None:
                        found.setdefault((o["description"], stat), []).append(float(o["point"]))
        rows += [{"game_id": "", "player_id": "", "player": p, "stat": s, "line": statistics.median(v),
                  "source": "The Odds API"} for (p, s), v in found.items()]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (US Eastern); default today")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    date = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(ET).date()
    slate_path = out / "slate" / f"{date}.csv"
    if not slate_path.exists():
        print("prop lines: no slate for", date)
        return
    slate = list(csv.DictReader(slate_path.open()))
    path = out / "props" / f"{date}.csv"
    old = list(csv.DictReader(path.open())) if path.exists() else []
    names = {}
    base = out / "baseline" / f"{date}.csv"
    if base.exists():
        for r in csv.DictReader(base.open()):
            names[r.get("player_id", "")] = r.get("player", "")
    now = dt.datetime.now(dt.timezone.utc)
    rows, open_games = [], []
    for g in slate:
        tip = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        if tip <= now:      # started: keep whatever pregame lines were saved earlier
            rows += [r for r in old if r.get("game_id") == g["game_id"]]
        else:
            open_games.append(g)
    got = 0
    for g in open_games:
        try:
            lines, book = espn_game(g["game_id"])
        except Exception as e:      # never fail the nightly run over lines
            print(f"prop lines: {g.get('name')} failed ({type(e).__name__}: {e})")
            lines, book = {}, None
        if not lines:               # keep earlier lines for this game if this fetch came back empty
            rows += [r for r in old if r.get("game_id") == g["game_id"]]
            continue
        got += len(lines)
        rows += [{"game_id": g["game_id"], "player_id": pid, "player": names.get(pid, ""), "stat": stat,
                  "line": line, "source": book} for (pid, stat), line in sorted(lines.items())]
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not got and open_games and key:
        try:
            rows += odds_api(date, key, names)
        except Exception as e:
            print(f"prop lines: The Odds API failed ({type(e).__name__})")
    if not rows:
        print("prop lines: none found")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, restval="")
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in COLS} for r in rows])
    print(f"prop lines: {len(rows)} saved to {path} ({got} fetched now, {len(open_games)} games not yet tipped)")


if __name__ == "__main__":
    main()
