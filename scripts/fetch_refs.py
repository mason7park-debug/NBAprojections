"""
Referee crews (2026-11-19). Collected only: nothing here moves a projection yet.

  python scripts/fetch_refs.py --out data              tonight's crews from official.nba.com
  python scripts/fetch_refs.py --out data --html FILE  same, from a saved copy of the page

The NBA posts each night's crews at about 9:00 am ET. They are matched to tonight's games
in data/slate/<date>.csv and saved to data/refs/nba/<date>.csv. Crews for finished games
come from ESPN's game summary instead (scripts/fetch_espn.py, data/refs/espn/<date>.csv),
so the history fills in even on days this page cannot be reached.

Why collect them: on 2026-11-19 (222 games, about 9 per referee) crews that had called the
most free throws in their other games called about 5.6 more per game, and stars scored 1.4
points above their projection with the heaviest-whistle crews and 0.7 below with the
lightest. Too few games per referee to trust yet, so the plan is to test again in late
December. Game totals and prop lines showed no crew effect.
"""
import argparse
import csv
import datetime as dt
import html
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

URL = "https://official.nba.com/referee-assignments/"
ET = ZoneInfo("America/New_York")

# The NBA page names teams by place; ESPN (and every other file here) by abbreviation.
TEAMS = {
    "atlanta": "ATL", "boston": "BOS", "brooklyn": "BKN", "charlotte": "CHA", "chicago": "CHI",
    "cleveland": "CLE", "dallas": "DAL", "denver": "DEN", "detroit": "DET", "golden state": "GS",
    "houston": "HOU", "indiana": "IND", "la clippers": "LAC", "los angeles clippers": "LAC",
    "la lakers": "LAL", "los angeles lakers": "LAL", "lakers": "LAL", "clippers": "LAC",
    "memphis": "MEM", "miami": "MIA", "milwaukee": "MIL", "minnesota": "MIN",
    "new orleans": "NO", "new york": "NY", "oklahoma city": "OKC", "orlando": "ORL",
    "philadelphia": "PHI", "phoenix": "PHX", "portland": "POR", "sacramento": "SAC",
    "san antonio": "SA", "toronto": "TOR", "utah": "UTAH", "washington": "WSH",
}


def team_ab(name):
    return TEAMS.get(re.sub(r"\s+", " ", name.strip().lower()))


def clean(cell):
    """'<a ...> Jacyn Goble (#68) </a>' -> ('Jacyn Goble', '68')"""
    text = html.unescape(re.sub(r"<[^>]+>", " ", cell))
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"(.*?)\s*\(#(\d+)\)$", text)
    return (m.group(1), m.group(2)) if m else (text, "")


def parse(page):
    """Date on the page and the NBA table's rows, ignoring the G League table under it."""
    m = re.search(r"NBA Referee Assignments.*?([A-Z][a-z]+ \d{1,2}, \d{4})", page, re.S)
    if not m:
        raise ValueError("no 'NBA Referee Assignments' date on the page")
    day = dt.datetime.strptime(m.group(1), "%B %d, %Y").date()
    rest = page[m.end():]
    t = re.search(r"<table.*?</table>", rest, re.S)
    if not t:
        raise ValueError("no assignments table after the NBA heading")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", t.group(0), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 4:
            continue
        game = clean(cells[0])[0]
        if "@" not in game:
            continue
        away, home = (s.strip() for s in game.split("@", 1))
        crew = [clean(c) for c in cells[1:5]] + [("", "")] * 4
        rows.append({"away_name": away, "home_name": home, "away": team_ab(away), "home": team_ab(home),
                     "crew_chief": crew[0][0], "crew_chief_no": crew[0][1],
                     "referee": crew[1][0], "referee_no": crew[1][1],
                     "umpire": crew[2][0], "umpire_no": crew[2][1],
                     "alternate": crew[3][0]})
    return day, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--html", help="parse a saved copy of the page instead of fetching it")
    a = ap.parse_args()
    out = Path(a.out)
    if a.html:
        page = Path(a.html).read_text()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (nba-projections; referee crews)"})
        try:
            page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception as e:      # the page is optional: a miss only means no crews tonight
            print(f"referee page not reachable: {e}")
            return 0
    try:
        day, rows = parse(page)
    except ValueError as e:
        print(f"referee page not read: {e}")
        return 0
    today = dt.datetime.now(ET).date()
    if not a.html and day != today:
        print(f"page still shows {day}, not {today} (it is posted about 9:00 am ET); nothing saved")
        return 0
    slate = {}
    sp = out / "slate" / f"{day}.csv"
    if sp.exists():
        with sp.open(newline="") as f:
            slate = {(r["away"], r["home"]): r["game_id"] for r in csv.DictReader(f)}
    for r in rows:
        r["game_id"] = slate.get((r["away"], r["home"]), "")
        if not r["home"] or not r["away"]:
            print(f"  team name not matched: {r['away_name']} @ {r['home_name']}")
    path = out / "refs" / "nba" / f"{day}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["game_id", "away", "home", "crew_chief", "crew_chief_no", "referee", "referee_no",
            "umpire", "umpire_no", "alternate", "away_name", "home_name"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}: {len(rows)} games, {sum(1 for r in rows if r['game_id'])} matched to the slate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
