"""
Nightly projections, floors, blowout risk and grading. No network access:
everything is read from the CSVs that fetch_espn.py committed under data/.

    python scripts/nightly.py project --date 2026-11-11
    python scripts/nightly.py grade   --date 2026-11-10

project  reads the pregame snapshot for --date (slate, odds, injuries) plus
         every box score before that date, and writes
           data/projections/<date>.csv   one row per player per stat
           docs/data/latest.json         what the results page shows
           docs/data/<date>.json         archive copy
grade    fills in what actually happened for --date and writes
           data/graded/<date>.csv
           docs/data/grade.json          last slate + all-nights record

The math in the MODEL section is the same code as the nba-projections skill.
Its constants are fixed on purpose. Grading reports how they are doing; it
never changes them. Change them by hand, in one commit, when the record says so.

Where each input comes from (all ESPN, via fetch_espn.py):
  player rates, minutes, logs   data/boxscores/*.csv (season to date)
  starters                      'starter' flag in recent box scores
  position (G / F / C)          'pos' in box scores
  defense by position           box scores, grouped by opponent and position
  area defense, pace            data/teamstats/*.csv (threes, paint, free throws)
  spread, total                 data/odds/<date>.csv
  injuries                      data/injuries/<date>.csv
  prop lines (optional)         data/props/<date>.csv  (player, stat, line)
"""

import argparse, csv, datetime as dt, json, math, pathlib, random, re, statistics, unicodedata
from collections import defaultdict

STATS = ["PTS", "REB", "AST", "3PM"]
CEIL_STATS = ["PTS", "REB", "AST", "3PM", "STL", "BLK"]
BENCH_MIN = 18.0      # bench players at or above this many minutes are projected
STAR_PPG = 18.0
BUMP_PPG = 20.0

# ============================================================== MODEL (fixed)
SD = 13.0          # spread of final margin around the point spread
BLOWOUT = 20       # a blowout is a final margin of 20 or more
FLOOR = {'PTS': 0.70, 'REB': 0.60, 'AST': 0.60, '3PM': 0.50}   # flat rule
MIN_LOG_GAMES = 6  # games needed before a player's own log sets his floor
RECENT_W = 0.4     # weight on recent form when the log has enough games

def blend(season, recent):
    return season if recent is None else (1 - RECENT_W) * season + RECENT_W * recent

def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def p_blowout(spread):
    s = abs(spread)
    return (1 - phi((BLOWOUT - s) / SD)) + (1 - phi((BLOWOUT + s) / SD))

def shrink(f, games, full_at):
    # pull a factor toward 1.0 while the sample is small
    return 1 + (f - 1) * min(1.0, games / full_at)

def cap(f):
    return max(0.85, min(1.15, f))

def zone_factor_pts(pts, tp, ft, f3, fpaint, fft):
    # weight each area of the floor by where this player's points come from
    if pts <= 0: return 1.0
    s3 = min(1.0, 3 * tp / pts)
    sft = min(1.0 - s3, ft / pts)
    s2 = max(0.0, 1 - s3 - sft)
    return s3 * f3 + s2 * fpaint + sft * fft

def matchup(stat, dvp_factor, opp_games, zone=None):
    pos = shrink(dvp_factor, opp_games, 40)
    if stat in ('PTS', '3PM') and zone is not None:
        return cap(0.7 * shrink(zone, opp_games, 20) + 0.3 * pos)
    return cap(pos)

def blowout_minutes(mpg):
    if mpg >= 30: return mpg * 0.80
    if mpg >= 24: return mpg * 0.90
    return mpg

def p20(values):
    v = sorted(values)
    k = 0.2 * (len(v) - 1)
    lo = int(math.floor(k)); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)

def project(per_game, mpg, m, pace_factor, pb, stat, bump=1.0, log_rates=None, recent_rate=None, recent_min=None):
    rate = blend(per_game / mpg, recent_rate)
    minutes = blend(mpg, recent_min)
    mult = m * pace_factor * bump
    bmin = blowout_minutes(minutes)
    normal = rate * minutes * mult
    blow = rate * bmin * mult
    expected = (1 - pb) * normal + pb * blow
    if log_rates is not None and len(log_rates) >= MIN_LOG_GAMES:
        floor, source = math.floor(p20(log_rates) * bmin * mult), 'log'
    else:
        floor, source = math.floor(blow * FLOOR[stat]), 'flat'
    return round(normal, 1), round(blow, 1), round(expected, 1), floor, source, round(minutes, 1)

SIMS = 10000
SEED = 2026
MIN_SD = 3.0                                   # night-to-night swing in minutes
CV = {'PTS': 0.30, 'REB': 0.35, 'AST': 0.40}   # used when a player has no usable log

def poisson(lam, rng):
    if lam <= 0: return 0
    limit = math.exp(-lam); k = 0; p = 1.0
    while True:
        p *= rng.random()
        if p <= limit: return k
        k += 1

def pct(sorted_vals, q):
    k = q * (len(sorted_vals) - 1)
    lo = int(math.floor(k)); hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)

def simulate_game(home_spread, players, game_index):
    rng = random.Random(SEED + game_index)
    out = {p['name']: {s: [] for s in p['stats']} for p in players}
    blow_flags = []
    for _ in range(SIMS):
        margin = rng.gauss(-home_spread, SD)
        blow = abs(margin) >= BLOWOUT
        blow_flags.append(blow)
        for p in players:
            base = blowout_minutes(p['minutes']) if blow else p['minutes']
            mins = max(0.0, rng.gauss(base, MIN_SD))
            for s, d in p['stats'].items():
                mean = d['rate'] * mins * d['mult']
                if s == '3PM':
                    v = poisson(mean, rng)
                else:
                    lr = d.get('log_rates')
                    if lr and len(lr) >= MIN_LOG_GAMES and sum(lr) > 0:
                        v = rng.choice(lr) / (sum(lr) / len(lr)) * mean
                    else:
                        v = max(0.0, rng.gauss(mean, CV[s] * mean))
                    v = int(v + 0.5)
                out[p['name']][s].append(v)
    return out, blow_flags

def summarize(vals, blow_flags, line=None):
    sv = sorted(vals)
    bv = sorted(v for v, b in zip(vals, blow_flags) if b)
    res = {'sim_mean': round(sum(vals) / len(vals), 1),
           'floor': int(pct(sv, 0.20)),
           'blowout_floor': int(pct(bv, 0.20)) if len(bv) >= 200 else None,
           'p_over': None}
    if line is not None:
        res['p_over'] = round(sum(1 for v in vals if v > line) / len(vals), 3)
    return res
# ========================================================== end MODEL (fixed)


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def made(v):
    try:
        return float(str(v).split("-")[0])
    except (ValueError, IndexError):
        return 0.0

def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else []
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

def norm(name):
    """Same player, different spellings: drop accents, punctuation and suffixes."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z ]", "", n)
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv"))

def tag(pb):
    return "Low" if pb < 0.15 else ("Medium" if pb <= 0.25 else "High")


# ------------------------------------------------------------------- history

def load_history(data, before):
    """Every finished game before `before` (a date). Returns player and team logs."""
    players = defaultdict(lambda: {"name": None, "games": []})
    team_games = defaultdict(list)      # team -> list of that team's game rows
    allowed_pos = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # team -> gid -> (pos,stat)
    for path in sorted((data / "teamstats").glob("*.csv")):
        d = dt.date.fromisoformat(path.stem)
        if d >= before:
            continue
        rows = read_csv(path)
        for r in rows:
            r["_date"] = d
            team_games[r["team"]].append(r)
        opp_of = {(r["game_id"], r["team"]): r["opp"] for r in rows}
        for r in read_csv(data / "boxscores" / f"{path.stem}.csv"):
            if str(r.get("dnp", "")).lower() == "true":
                continue
            mins = fnum(r.get("MIN"), 0.0)
            if not mins:
                continue
            g = {"date": d, "team": r["team"], "MIN": mins,
                 "PTS": fnum(r.get("PTS"), 0.0), "REB": fnum(r.get("REB"), 0.0),
                 "AST": fnum(r.get("AST"), 0.0), "3PM": made(r.get("3PT")),
                 "FTM": made(r.get("FT")),
                 "starter": str(r.get("starter", "")).lower() == "true",
                 "pos": (r.get("pos") or "F")[-1] if (r.get("pos") or "") not in ("G", "F", "C") else r.get("pos")}
            p = players[r["player_id"]]
            p["name"] = r["player"]
            p["games"].append(g)
            opp = opp_of.get((r["game_id"], r["team"]))
            if opp:
                for s in STATS:
                    allowed_pos[opp][r["game_id"]][(g["pos"], s)] += g[s]
    return players, team_games, allowed_pos


def team_tables(team_games, allowed_pos):
    """Per-team defense and pace, each already divided by league average."""
    def poss(r):
        v = [fnum(r.get(k)) for k in ("FGA", "OREB", "TOV", "FTA")]
        return None if None in v else v[0] - v[1] + v[2] + 0.44 * v[3]

    by_game = {(r["game_id"], r["team"]): r for rows in team_games.values() for r in rows}
    raw = {}
    for team, rows in team_games.items():
        allow = defaultdict(list); pace = []
        for r in rows:
            o = by_game.get((r["game_id"], r["opp"]))
            if not o:
                continue
            for s in CEIL_STATS + ["FTM", "PAINT"]:
                v = fnum(o.get(s))
                if v is not None:
                    allow[s].append(v)
            a, b = poss(r), poss(o)
            if a is not None and b is not None:
                pace.append((a + b) / 2)
        raw[team] = {"games": len(rows),
                     "allow": {s: statistics.mean(v) for s, v in allow.items() if v},
                     "pace": statistics.mean(pace) if pace else None}
    lg = {}
    for s in CEIL_STATS + ["FTM", "PAINT"]:
        vals = [t["allow"][s] for t in raw.values() if s in t["allow"]]
        lg[s] = statistics.mean(vals) if vals else None
    paces = [t["pace"] for t in raw.values() if t["pace"]]
    lg_pace = statistics.mean(paces) if paces else None

    # defense vs position: per game allowed to each position group
    dvp_raw = defaultdict(dict)
    for team, games in allowed_pos.items():
        n = len(games)
        for pos in ("G", "F", "C"):
            for s in STATS:
                dvp_raw[team][(pos, s)] = sum(g.get((pos, s), 0.0) for g in games.values()) / n
    dvp = defaultdict(dict)
    for key in [(p, s) for p in ("G", "F", "C") for s in STATS]:
        vals = [dvp_raw[t][key] for t in dvp_raw]
        avg = statistics.mean(vals) if vals else 0
        for t in dvp_raw:
            dvp[t][key] = dvp_raw[t][key] / avg if avg else 1.0
    return raw, lg, lg_pace, dvp


def player_profile(p):
    g = p["games"]
    n = len(g)
    mpg = sum(x["MIN"] for x in g) / n
    prof = {"name": p["name"], "gp": n, "mpg": mpg, "team": g[-1]["team"],
            "pos": max(("G", "F", "C"), key=lambda k: sum(1 for x in g if x["pos"] == k)),
            "last_date": g[-1]["date"],
            "start_share": sum(1 for x in g[-5:] if x["starter"]) / len(g[-5:]),
            "FTM": sum(x["FTM"] for x in g) / n}
    for s in STATS:
        prof[s] = sum(x[s] for x in g) / n
    last5 = g[-5:]
    prof["recent_min"] = sum(x["MIN"] for x in last5) / len(last5) if len(last5) >= 3 else None
    q = [x for x in g if x["MIN"] >= 15]
    last10 = q[-10:]
    prof["log_rates"] = {s: [x[s] / x["MIN"] for x in q] for s in STATS}
    tot_min = sum(x["MIN"] for x in last10)
    prof["recent_rate"] = ({s: sum(x[s] for x in last10) / tot_min for s in STATS}
                           if len(last10) >= 5 and tot_min else None)
    return prof


# ------------------------------------------------------------------- project

def run_project(date, data, docs):
    slate = read_csv(data / "slate" / f"{date}.csv")
    if not slate:
        print(f"no games found for {date}; nothing to project")
        return
    odds = {r["game_id"]: r for r in read_csv(data / "odds" / f"{date}.csv")}
    inj = read_csv(data / "injuries" / f"{date}.csv")
    out_ids = {r["player_id"] for r in inj if (r.get("status") or "").lower() == "out"}
    gtd_ids = {r["player_id"] for r in inj if (r.get("status") or "").lower() != "out"}
    lines = {(norm(r["player"]), r["stat"]): fnum(r["line"]) for r in read_csv(data / "props" / f"{date}.csv")}

    players, team_games, allowed_pos = load_history(data, date)
    raw, lg, lg_pace, dvp = team_tables(team_games, allowed_pos)
    profs = {pid: player_profile(p) for pid, p in players.items() if p["games"]}
    by_team = defaultdict(list)
    for pid, pr in profs.items():
        by_team[pr["team"]].append((pid, pr))

    def pool(team):
        recent_dates = sorted({r["_date"] for r in team_games.get(team, [])})[-4:]
        cutoff = recent_dates[0] if recent_dates else date
        cands = []
        for pid, pr in by_team.get(team, []):
            if pid in out_ids:
                continue
            if pr["last_date"] < cutoff and pid not in gtd_ids:
                continue          # has not played lately and is not on the report
            cands.append((pid, pr))
        starters = sorted([c for c in cands if c[1]["start_share"] >= 0.5],
                          key=lambda c: (-c[1]["start_share"], -c[1]["mpg"]))[:5]
        sid = {c[0] for c in starters}
        if len(starters) < 5:      # fill open spots with the heaviest-minute players left
            rest = sorted([c for c in cands if c[0] not in sid and c[1]["gp"] >= 3],
                          key=lambda c: (-c[1]["start_share"], -c[1]["recent_min"] if c[1]["recent_min"] else -c[1]["mpg"]))
            starters += rest[:5 - len(starters)]
            sid = {c[0] for c in starters}
        bench = sorted([c for c in cands if c[0] not in sid and c[1]["mpg"] >= BENCH_MIN and c[1]["gp"] >= 3],
                       key=lambda c: -c[1]["mpg"])
        return starters, bench

    def out_scorers(team):
        return [pr["name"] for pid, pr in by_team.get(team, [])
                if pid in out_ids and pr["PTS"] >= BUMP_PPG]

    games_out, proj_rows, notes = [], [], []
    slate = sorted(slate, key=lambda r: (r["date"], r["game_id"]))
    for gi, g in enumerate(slate):
        home, away, gid = g["home"], g["away"], g["game_id"]
        o = odds.get(gid, {})
        spread, total = fnum(o.get("spread")), fnum(o.get("over_under"))
        if spread is None:
            notes.append(f"{away} at {home}: no spread posted at fetch time, treated as an even game.")
        pb = p_blowout(spread if spread is not None else 0.0)
        ph, pa = raw.get(home, {}).get("pace"), raw.get(away, {}).get("pace")
        pace_factor = ((ph + pa) / 2 / lg_pace) if ph and pa and lg_pace else 1.0

        ceil = {}
        for s in CEIL_STATS:
            a, b = raw.get(home, {}).get("allow", {}).get(s), raw.get(away, {}).get("allow", {}).get(s)
            ceil[s] = round((a + b) / 2 / lg[s], 3) if a and b and lg.get(s) else None

        sim_players, team_blocks = [], []
        for team, opp in ((away, home), (home, away)):
            od = raw.get(opp, {"games": 0, "allow": {}})
            area = {k: (od["allow"][src] / lg[src] if src in od["allow"] and lg.get(src) else 1.0)
                    for k, src in (("f3", "3PM"), ("fpaint", "PAINT"), ("fft", "FTM"))}
            outs = out_scorers(team)
            bump_val = min(1.10, 1.0 + 0.05 * len(outs))
            starters, bench = pool(team)
            rows = []
            for role, group in (("starter", starters), ("bench", bench)):
                for pid, pr in group:
                    entry = {"id": pid, "name": pr["name"], "team": team, "opp": opp, "pos": pr["pos"],
                             "role": role, "gtd": pid in gtd_ids, "star": pr["PTS"] >= STAR_PPG,
                             "season": {s: round(pr[s], 1) for s in STATS}, "mpg": round(pr["mpg"], 1),
                             "stats": {}}
                    sim_stats = {}
                    for s in STATS:
                        f = dvp.get(opp, {}).get((pr["pos"], s), 1.0)
                        zone = None
                        if s == "PTS":
                            zone = zone_factor_pts(pr["PTS"], pr["3PM"], pr["FTM"], area["f3"], area["fpaint"], area["fft"])
                        elif s == "3PM":
                            zone = area["f3"]
                        m = matchup(s, f, od["games"], zone)
                        bump = bump_val if s in ("PTS", "AST") else 1.0
                        lr = pr["log_rates"][s] or None
                        rr = pr["recent_rate"][s] if pr["recent_rate"] else None
                        normal, blow, expected, rfloor, src, minutes = project(
                            pr[s], pr["mpg"], m, pace_factor, pb, s, bump, lr, rr, pr["recent_min"])
                        entry["min"] = minutes
                        entry["stats"][s] = {"normal": normal, "blowout": blow, "expected": expected,
                                             "rule_floor": rfloor, "floor_source": src,
                                             "matchup": round(m, 3), "line": lines.get((norm(pr["name"]), s))}
                        sim_stats[s] = {"rate": blend(pr[s] / pr["mpg"], rr), "mult": m * pace_factor * bump,
                                        "log_rates": lr}
                    sim_players.append({"name": pid, "minutes": entry["min"], "stats": sim_stats})
                    rows.append(entry)
            team_blocks.append({"team": team, "opp": opp, "area": {k: round(v, 3) for k, v in area.items()},
                                "out_scorers": outs, "players": rows})

        sims, flags = simulate_game(spread if spread is not None else 0.0, sim_players, gi)
        for tb in team_blocks:
            for e in tb["players"]:
                for s in STATS:
                    st = e["stats"][s]
                    res = summarize(sims[e["id"]][s], flags, st["line"])
                    st.update(floor=res["floor"], blowout_floor=res["blowout_floor"],
                              p_over=res["p_over"], sim_mean=res["sim_mean"])
                    st["gap"] = (res["floor"] - st["line"]) if st["line"] is not None else None
                    st["check"] = bool(st["line"] and abs(st["expected"] - st["line"]) / st["line"] >= 0.20)
                    if st["expected"] >= 5 and abs(res["sim_mean"] - st["expected"]) / st["expected"] > 0.05:
                        notes.append(f"{e['name']} {s}: simulation average {res['sim_mean']} vs expected {st['expected']}.")
                    proj_rows.append({
                        "date": str(date), "game_id": gid, "player_id": e["id"], "player": e["name"],
                        "team": e["team"], "opp": e["opp"], "role": e["role"], "star": e["star"], "stat": s,
                        "minutes": e["min"], "normal": st["normal"], "blowout": st["blowout"],
                        "expected": st["expected"], "floor": st["floor"], "blowout_floor": st["blowout_floor"],
                        "p_over": st["p_over"], "rule_floor": st["rule_floor"],
                        "floor_source": st["floor_source"], "line": st["line"],
                        "spread": spread, "p_blowout": round(pb, 3)})
        games_out.append({"game_id": gid, "home": home, "away": away, "tip": g["date"],
                          "spread": spread, "total": total, "favorite": o.get("details"),
                          "p_blowout": round(pb, 3), "tag": tag(pb) if spread is not None else None,
                          "pace": round(pace_factor, 3), "ceiling": ceil, "teams": team_blocks})

    # target games by stat
    targets = {}
    for s in CEIL_STATS:
        ranked = sorted([g for g in games_out if g["ceiling"].get(s)],
                        key=lambda g: (-g["ceiling"][s], -(g["total"] or 0)))
        picks = []
        for g in ranked[:2]:
            if g["ceiling"][s] < 1.03:
                continue
            tops = []
            if s in STATS:
                everyone = [e for tb in g["teams"] for e in tb["players"]]
                tops = [{"name": e["name"], "team": e["team"], "expected": e["stats"][s]["expected"]}
                        for e in sorted(everyone, key=lambda e: -e["stats"][s]["expected"])[:3]]
            picks.append({"away": g["away"], "home": g["home"], "index": g["ceiling"][s],
                          "total": g["total"], "tag": g["tag"], "players": tops})
        targets[s] = picks

    # safest lines / floors
    flat = [(e, s, e["stats"][s]) for g in games_out for tb in g["teams"] for e in tb["players"] for s in STATS]
    with_line = sorted([x for x in flat if x[2]["p_over"] is not None], key=lambda x: -x[2]["p_over"])
    no_line = sorted([x for x in flat if x[2]["line"] is None and x[0]["star"] and x[2]["expected"] >= 3],
                     key=lambda x: -(x[2]["floor"] / x[2]["expected"]))
    safest = [{"name": e["name"], "team": e["team"], "stat": s, "line": st["line"], "p_over": st["p_over"],
               "floor": st["floor"], "blowout_floor": st["blowout_floor"], "expected": st["expected"]}
              for e, s, st in (with_line + no_line)[:10]]

    hist_dates = sorted({r["_date"] for rows in team_games.values() for r in rows})
    n_log = sum(1 for r in proj_rows if r["floor_source"] == "log")
    now_et = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)
    first_tip = min(dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00")) for g in slate)
    hours_early = (first_tip - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
    payload = {
        "date": str(date), "run_time_et": now_et.strftime("%Y-%m-%d %I:%M %p ET"),
        "early_run": hours_early > 3,
        "games": games_out, "targets": targets, "safest": safest,
        "method": {
            "history_days": len(hist_dates),
            "history_from": str(hist_dates[0]) if hist_dates else None,
            "history_to": str(hist_dates[-1]) if hist_dates else None,
            "log_floors": n_log, "flat_floors": len(proj_rows) - n_log,
            "lines_found": sum(1 for r in proj_rows if r["line"] is not None),
            "players": len(proj_rows) // len(STATS),
            "notes": notes[:40],
        },
    }
    write_csv(proj_rows, data / "projections" / f"{date}.csv")
    (docs / "data").mkdir(parents=True, exist_ok=True)
    for name in ("latest.json", f"{date}.json"):
        (docs / "data" / name).write_text(json.dumps(payload, separators=(",", ":")))
    print(f"projected {payload['method']['players']} players in {len(games_out)} games for {date}")
    print(f"floors: {n_log} from player logs, {len(proj_rows) - n_log} flat rule; lines found: {payload['method']['lines_found']}")


# --------------------------------------------------------------------- grade

def grade_one(date, data):
    proj = read_csv(data / "projections" / f"{date}.csv")
    box = read_csv(data / "boxscores" / f"{date}.csv")
    teams = read_csv(data / "teamstats" / f"{date}.csv")
    if not proj or not box or not teams:
        return None
    margin = {(r["game_id"], r["team"]): abs(fnum(r["margin"], 0)) for r in teams}
    act = {}
    for r in box:
        played = str(r.get("dnp", "")).lower() != "true" and fnum(r.get("MIN"), 0) > 0
        act[r["player_id"]] = {"played": played, "MIN": fnum(r.get("MIN"), 0.0),
                               "PTS": fnum(r.get("PTS"), 0.0), "REB": fnum(r.get("REB"), 0.0),
                               "AST": fnum(r.get("AST"), 0.0), "3PM": made(r.get("3PT"))}
    out = []
    for r in proj:
        a = act.get(r["player_id"])
        r = dict(r)
        r["played"] = bool(a and a["played"])
        r["actual"] = a[r["stat"]] if r["played"] else ""
        r["actual_minutes"] = a["MIN"] if r["played"] else ""
        r["final_margin"] = margin.get((r["game_id"], r["team"]), "")
        out.append(r)
    write_csv(out, data / "graded" / f"{date}.csv")
    return out


def summarize_grades(rows):
    played = [r for r in rows if str(r["played"]) == "True"]
    res = {"player_games": len({(r["date"], r["player_id"]) for r in played})}
    def f(r, k):
        return fnum(r[k])
    acc = {}
    for s in STATS:
        q = [r for r in played if r["stat"] == s]
        if not q:
            continue
        d = [f(r, "actual") - f(r, "expected") for r in q]
        fl = [r for r in q if f(r, "floor") is not None]
        bl = [r for r in q if f(r, "blowout_floor") is not None and fnum(r["final_margin"], 0) >= BLOWOUT]
        acc[s] = {"n": len(q), "bias": round(statistics.mean(d), 2),
                  "mae": round(statistics.mean(abs(x) for x in d), 2),
                  "floor_hit": round(sum(f(r, "actual") >= f(r, "floor") for r in fl) / len(fl), 3) if fl else None,
                  "blowout_floor_hit": round(sum(f(r, "actual") >= f(r, "blowout_floor") for r in bl) / len(bl), 3) if bl else None,
                  "blowout_floor_n": len(bl)}
        for src in ("log", "flat"):
            z = [r for r in q if r["floor_source"] == src]
            acc[s][f"rule_floor_hit_{src}"] = (round(sum(f(r, "actual") >= f(r, "rule_floor") for r in z) / len(z), 3) if z else None)
            acc[s][f"rule_floor_n_{src}"] = len(z)
    res["stats"] = acc
    stars = [r for r in played if r["stat"] == "PTS" and str(r["star"]) == "True"]
    res["star_floors"] = len(stars)
    res["star_floor_hit"] = round(sum(f(r, "actual") >= f(r, "floor") for r in stars) / len(stars), 3) if stars else None
    for label, test in (("close", lambda m: m < BLOWOUT), ("blowout", lambda m: m >= BLOWOUT)):
        z = [r for r in stars if test(fnum(r["final_margin"], 0))]
        res[f"star_minutes_{label}"] = ({"n": len(z), "projected": round(statistics.mean(f(r, "minutes") for r in z), 1),
                                         "actual": round(statistics.mean(f(r, "actual_minutes") for r in z), 1)} if z else None)
    buckets = [("under 50%", 0, .5), ("50 to 70%", .5, .7), ("70 to 85%", .7, .85), ("85% and up", .85, 1.01)]
    lined = [r for r in played if f(r, "p_over") is not None and f(r, "line") is not None]
    res["over_check"] = [{"bucket": b, "n": len(z), "went_over": round(sum(f(r, "actual") > f(r, "line") for r in z) / len(z), 3)}
                         for b, lo, hi in buckets for z in [[r for r in lined if lo <= f(r, "p_over") < hi]] if z]
    res["line_check"] = ({"n": len(lined),
                          "model_mae": round(statistics.mean(abs(f(r, "actual") - f(r, "expected")) for r in lined), 2),
                          "line_mae": round(statistics.mean(abs(f(r, "actual") - f(r, "line")) for r in lined), 2)} if lined else None)
    games = {}
    for r in rows:
        games[(r["date"], r["game_id"])] = (fnum(r["p_blowout"], 0), fnum(r["final_margin"]), r["team"], r["opp"])
    res["blowout_by_tag"] = {}
    for t in ("Low", "Medium", "High"):
        z = [g for g in games.values() if tag(g[0]) == t and g[1] is not None]
        res["blowout_by_tag"][t] = {"games": len(z), "ended_by_20": sum(1 for g in z if g[1] >= BLOWOUT)}
    return res, games


def run_grade(date, data, docs):
    rows = grade_one(date, data)
    if rows is None:
        print(f"nothing to grade for {date} (need projections, box scores and team stats)")
        return
    last, games = summarize_grades(rows)
    last["date"] = str(date)
    last["did_not_play"] = sorted({r["player"] for r in rows if str(r["played"]) != "True"})
    last["blowout_calls"] = [{"game": f"{g[3]} / {g[2]}", "p_blowout": g[0], "margin": g[1]}
                             for g in sorted(games.values(), key=lambda g: -g[0])]
    every = []
    for p in sorted((data / "graded").glob("*.csv")):
        every.extend(read_csv(p))
    allnights, _ = summarize_grades(every)
    allnights["nights"] = len({r["date"] for r in every})
    (docs / "data").mkdir(parents=True, exist_ok=True)
    (docs / "data" / "grade.json").write_text(json.dumps({"last": last, "all": allnights}, separators=(",", ":")))
    s = last["stats"].get("PTS", {})
    print(f"graded {date}: {last['player_games']} player-games, PTS bias {s.get('bias')} MAE {s.get('mae')}, "
          f"floor hit {s.get('floor_hit')}; all nights: {allnights['nights']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["project", "grade"])
    ap.add_argument("--date", help="YYYY-MM-DD; default is today (US Eastern) for project, yesterday for grade")
    ap.add_argument("--data", default="data")
    ap.add_argument("--docs", default="docs")
    a = ap.parse_args()
    today = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).date()
    if a.date:
        date = dt.date.fromisoformat(a.date)
    else:
        date = today if a.cmd == "project" else today - dt.timedelta(days=1)
    data, docs = pathlib.Path(a.data), pathlib.Path(a.docs)
    (run_project if a.cmd == "project" else run_grade)(date, data, docs)


if __name__ == "__main__":
    main()
