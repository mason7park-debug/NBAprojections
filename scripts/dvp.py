"""
Defense vs position (DvP) from season box scores.

ESPN exposes no opponent-split team stats (its "defensive" category is only
DR/STL/BLK), so this derives DvP the long way: walk every box score of the
season, attribute each player's production to the position he plays and the
team he played against, and compare each defense to the league average.

    python scripts/dvp.py --through 2026-11-07 --days 30 --out data/dvp

Output: data/dvp/<date>.csv with one row per (team, position) holding points,
rebounds, assists and threes allowed per game, plus a ratio against league
average. Ratio > 1.00 means that defense gives up MORE than average to that
position, i.e. a good matchup for the opposing player.

CAVEATS, which matter more than the numbers:
  - Early season. ~175 games means roughly 12 per team, so each (team,
    position) cell rests on ~12 games. That is thin, and the extremes are
    mostly noise.
  - Not opponent-adjusted. A defense that has faced weak offenses looks good.
  - Position labels are ESPN's single listed position. Real lineups are
    positionless; a "C" guarded by a PF is still booked as production allowed
    to C.
  - Garbage time is included, which inflates production allowed by teams that
    win big.
Treat a ratio as a weak prior, not a projection input, until there is enough
of a sample to validate it.
"""

import argparse, csv, collections, datetime as dt, json, pathlib, sys, time
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
UA = "nba-projections/1.0 (personal research project)"
PAUSE = 0.25
STATS = ["PTS", "REB", "AST", "3PM"]


def get(url, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=30) as f:
                d = json.load(f)
            time.sleep(PAUSE)
            return d
        except Exception:
            time.sleep(1.5 ** i)
    return None


def simplify(pos):
    """ESPN lists PG/SG/SF/PF/C and hybrids like 'C-F'. Take the first token."""
    if not pos:
        return None
    p = pos.split("-")[0].strip().upper()
    return {"G": "G", "PG": "PG", "SG": "SG", "F": "F",
            "SF": "SF", "PF": "PF", "C": "C"}.get(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", default=str(dt.date.today()))
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="data/dvp")
    ap.add_argument("--positions", default="data/baseline")
    a = ap.parse_args()

    end = dt.date.fromisoformat(a.through)

    # Player -> position, from the most recent baseline snapshot.
    posdir = pathlib.Path(a.positions)
    snaps = sorted(posdir.glob("*.csv"))
    if not snaps:
        raise SystemExit(f"no baseline snapshot in {posdir}; run fetch_espn.py first")
    pos = {}
    for r in csv.DictReader(snaps[-1].open()):
        p = simplify(r.get("position"))
        if p:
            pos[r["player"]] = p
    print(f"positions for {len(pos)} players (from {snaps[-1].name})")

    # Collect game ids.
    gids = []
    for i in range(1, a.days + 1):
        day = (end - dt.timedelta(days=i)).strftime("%Y%m%d")
        sb = get(f"{SITE}/scoreboard?dates={day}")
        if not sb:
            continue
        for e in sb.get("events", []):
            st = ((e.get("status") or {}).get("type") or {}).get("name", "")
            if "FINAL" in st.upper():
                gids.append(e["id"])
    print(f"{len(gids)} completed games in the last {a.days} days")

    # allowed[(defteam, position)] -> list of per-game totals
    allowed = collections.defaultdict(lambda: collections.defaultdict(float))
    gamecount = collections.defaultdict(set)

    for n, gid in enumerate(gids, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(gids)}", file=sys.stderr)
        d = get(f"{SITE}/summary?event={gid}")
        if not d:
            continue
        blocks = (d.get("boxscore") or {}).get("players", [])
        teams = [(b.get("team") or {}).get("abbreviation") for b in blocks]
        if len(teams) != 2:
            continue
        for idx, blk in enumerate(blocks):
            opp = teams[1 - idx]           # the defense being scored against
            for sb in blk.get("statistics", []):
                labels = sb.get("labels", [])
                for ath in sb.get("athletes", []):
                    if ath.get("didNotPlay"):
                        continue
                    name = (ath.get("athlete") or {}).get("displayName")
                    p = pos.get(name)
                    if not p:
                        continue
                    vals = dict(zip(labels, ath.get("stats", [])))
                    def num(k):
                        try: return float(vals.get(k, 0) or 0)
                        except: return 0.0
                    tp = str(vals.get("3PT", "0-0"))
                    tpm = float(tp.split("-")[0]) if "-" in tp and tp.split("-")[0].isdigit() else 0.0
                    allowed[(opp, p)]["PTS"] += num("PTS")
                    allowed[(opp, p)]["REB"] += num("REB")
                    allowed[(opp, p)]["AST"] += num("AST")
                    allowed[(opp, p)]["3PM"] += tpm
                    gamecount[(opp, p)].add(gid)

    # Per-game rates, then league average per position.
    rows = []
    for (team, p), tot in allowed.items():
        g = len(gamecount[(team, p)])
        if g < 3:
            continue
        rows.append({"team": team, "pos": p, "games": g,
                     **{s: tot[s] / g for s in STATS}})

    lg = {}
    for p in {r["pos"] for r in rows}:
        sub = [r for r in rows if r["pos"] == p]
        lg[p] = {s: sum(r[s] for r in sub) / len(sub) for s in STATS}

    for r in rows:
        for s in STATS:
            base = lg[r["pos"]][s]
            r[f"{s}_ratio"] = (r[s] / base) if base else 1.0

    outp = pathlib.Path(a.out) / f"{a.through}.csv"
    outp.parent.mkdir(parents=True, exist_ok=True)
    cols = ["team", "pos", "games"] + STATS + [f"{s}_ratio" for s in STATS]
    with outp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["team"], r["pos"])):
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in r.items()})
    print(f"wrote {outp} ({len(rows)} team-position cells)")


if __name__ == "__main__":
    main()
