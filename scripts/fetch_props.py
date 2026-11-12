"""
Optional: player prop lines from The Odds API (the-odds-api.com).

    ODDS_API_KEY=... python scripts/fetch_props.py --date 2026-11-11

Writes data/props/<date>.csv with columns player, stat, line, books.
The line is the middle (median) line across the books that list the player.
Lines never feed the projection. They sit beside it as an outside check.

If ODDS_API_KEY is not set this does nothing and exits cleanly, so the
nightly run works with or without it.

Each game costs one request per market. PROP_MARKETS picks the markets
(default: points only, to stay inside a free plan). All four:
    PROP_MARKETS=player_points,player_rebounds,player_assists,player_threes

NOTE: written from the API's public documentation and not yet run with a
real key. Check the first night's file before trusting it.
"""
import argparse, csv, datetime as dt, json, os, pathlib, statistics, sys, urllib.parse, urllib.request

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"
STAT = {"player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST", "player_threes": "3PM"}


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (US Eastern); default today")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        print("ODDS_API_KEY not set; skipping prop lines")
        return
    et = dt.timezone(dt.timedelta(hours=-5))
    date = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(et).date()
    markets = os.environ.get("PROP_MARKETS", "").strip() or "player_points"
    try:
        events = get(f"{BASE}/events?apiKey={urllib.parse.quote(key)}")
    except Exception as e:                       # never fail the nightly run over lines
        print(f"prop lines: could not list games ({type(e).__name__})")
        return
    found = {}
    for ev in events:
        tip = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(et)
        if tip.date() != date:
            continue
        url = (f"{BASE}/events/{ev['id']}/odds?apiKey={urllib.parse.quote(key)}"
               f"&regions=us&oddsFormat=american&markets={markets}")
        try:
            data = get(url)
        except Exception as e:
            print(f"prop lines: {ev.get('away_team')} at {ev.get('home_team')} failed ({type(e).__name__})")
            continue
        for book in data.get("bookmakers", []):
            for m in book.get("markets", []):
                stat = STAT.get(m.get("key"))
                if not stat:
                    continue
                for o in m.get("outcomes", []):
                    if o.get("name") == "Over" and o.get("description") and o.get("point") is not None:
                        found.setdefault((o["description"], stat), []).append(float(o["point"]))
    rows = [{"player": p, "stat": s, "line": statistics.median(v), "books": len(v)}
            for (p, s), v in sorted(found.items())]
    if not rows:
        print("prop lines: none found")
        return
    path = pathlib.Path(a.out) / "props" / f"{date}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["player", "stat", "line", "books"])
        w.writeheader()
        w.writerows(rows)
    print(f"prop lines: wrote {len(rows)} to {path}")


if __name__ == "__main__":
    main()
