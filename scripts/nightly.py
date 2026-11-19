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
  prop lines                    data/props/<date>.csv  (ESPN odds feed, via fetch_props.py)
"""

import argparse, csv, datetime as dt, json, math, os, pathlib, random, re, statistics, unicodedata
from collections import defaultdict
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")     # follows daylight saving time
STATS = ["PTS", "REB", "AST", "3PM"]
CEIL_STATS = ["PTS", "REB", "AST", "3PM", "STL", "BLK"]
BENCH_MIN = 18.0      # bench players at or above this many minutes are projected
STAR_PPG = 18.0
BUMP_PPG = 20.0
# Settings were frozen on this date. The plan: no changes until 15 live nights are graded,
# and then only changes that hold up on the live record as well as the replay.
MODEL_VERSION = "2026-11-19"   # 2026-11-18 (fill-in starters, first game back) + line anchor, over-chance calibration, ceilings at 95%, floor caps, home edge 1.5
LIVE_FROM = dt.date(2026, 11, 12)     # first slate projected before tip by the scheduled runs
# Percentile used for bench players' points floors. Everyone else uses the 20th.
# The 12th held 81% of 439 bench cases on the replay; the 20th held only 74%.
FLOOR_Q_BENCH_PTS = float(os.environ.get("NBA_FLOOR_Q_BENCH", 0.12))
# Calibration (2026-11-19, replayed on 11/13 to 11/18; logs/2026-11-19-calibration.md).
# Line anchor: where a prop line exists, the projection is LINE_W x the model's expected value +
# (1 - LINE_W) x the line, and the simulated games are scaled to match. The line beat the model as a
# projection (points miss 5.05 vs 5.28), and players went over about half the time wherever the line
# sat against their recent games. 1.0 = off.
LINE_W = float(os.environ.get("NBA_LINE_W", 0.25))
# Over chance: the simulation's chance of going over spread far wider than what happened (it said 27%
# where 47% went over, 64% where 56% did) and leaned under. Shrunk to a quarter of its lean, centered
# where the results were. "off" shows the raw simulation.
P_OVER_CAL = os.environ.get("NBA_P_OVER_CAL", "on")
CEIL_Q = float(os.environ.get("NBA_CEIL_Q", 0.95))      # ceiling percentile (0.90 was reached 16 to 26% of the time)
# Floors no closer than this to the expected value: tight floors for steady players were missed
# about 1 time in 4. 9 = no cap.
FLOOR_CAP = {"PTS": float(os.environ.get("NBA_FLOOR_CAP_PTS", 0.65)), "REB": float(os.environ.get("NBA_FLOOR_CAP_REB", 0.70)),
             "AST": float(os.environ.get("NBA_FLOOR_CAP_AST", 0.70)), "3PM": float(os.environ.get("NBA_FLOOR_CAP_TPM", 9))}
# Last season as a starting point. A player's per-minute rates and minutes are blended with
# last season's, counted as PRIOR_KMIN minutes and PRIOR_KG games of evidence, so the blend
# fades on its own as this season's sample grows. Team ratings for the game margin are blended
# the same way with PRIOR_TEAM_K games. Switched on 2026-11-12 after it beat the season
# average on all four stats on the replay (points miss 5.10 -> 5.05).
USE_PRIOR = os.environ.get("NBA_PRIOR", "on") == "on"
PRIOR_KMIN = 100.0
PRIOR_KG = 3.0
PRIOR_TEAM_K = 20.0
PRIOR_SEASON = "2025-26"
HOME_EDGE = float(os.environ.get("NBA_HOME_EDGE", 1.5))       # points the home team is worth (2.5 until 2026-11-19: home teams won by 1.0 on average, the model had them at 2.1)
RATE_K = float(os.environ.get("NBA_RATE_K", 10))           # team ratings are pulled toward average until about this many games
INJ_K = float(os.environ.get("NBA_INJ_K", 0.5))    # share of a missing player's scoring edge the team loses
B2B_PTS = float(os.environ.get("NBA_B2B", 1.5))    # points a team loses on the second night of a back-to-back
MIN_SD_STARTER = float(os.environ.get("NBA_MIN_SD_STARTER", 5.0))   # starters under 18 points a game (measured 5.3)
BUMP_MODE = os.environ.get("NBA_BUMP", "log")     # "log" = from each player's own games, "flat" = old +5% rule
# Matchup nudge for threes: "none", "pos" (position only) or "full" (threes allowed + position).
# "full" until 2026-11-12. On 1,232 replayed player-games neither kind of threes defense carried
# over, and dropping the nudge missed by slightly less (1.027 vs 1.030), so it is off. The nightly
# matchup check in the record shows whether that changes; pace still applies.
TPM_MATCHUP = os.environ.get("NBA_3PM_MATCHUP", "none")
BUMP_TRIGGER = 15.0   # a missing teammate scoring this much can move the others
BUMP_SHRINK = 4       # games without the teammate before the player's own numbers are trusted
MIN_SD_BENCH = float(os.environ.get("NBA_MIN_SD_BENCH", 6.0))   # bench minutes swing more than starters'
# Minutes fill (2026-11-18). A player ruled out leaves his minutes behind; before this the model
# gave them to nobody, so the fill-ins kept their usual minutes (CLE on 2026-11-14 had three
# players projected at 17 to 23 minutes who all played 34). Modes:
#   "promote"  ON. A player moved into the starting five plays PROMOTE_A + PROMOTE_B x his usual
#              minutes (fit on 148 promotions before 2026-11-12: a 16-minute player plays ~24).
#              With PROMOTE_POS "on" the open spot goes first to a player at the missing
#              starter's position. The only version that held up on both live and earlier nights.
#   "promote+" promote, then share what is left of the missing minutes by room (MIN_FILL_K)
#   "total"    scale everyone up until the team adds back to MIN_FILL_TARGET
#   "even"     share the missing minutes in proportion to usual minutes
#   "on"       share them by room to grow
#   "off"      the 2026-11-12b behavior
# Results for each: logs/2026-11-18-minutes-fill.md.
MIN_FILL = os.environ.get("NBA_MIN_FILL", "promote")
MIN_FILL_TARGET = float(os.environ.get("NBA_MIN_FILL_TARGET", 240.0))
MIN_FILL_MAX = float(os.environ.get("NBA_MIN_FILL_MAX", 1.25))
MIN_FILL_CAP = 40.0
PROMOTE_POS = os.environ.get("NBA_PROMOTE_POS", "on")   # "on": fill an open starting spot by position first
PROMOTE_HIST = os.environ.get("NBA_PROMOTE_HIST", "off")   # "on": pick the fill-in from who started when that starter sat before
PROMOTE_HIST_K = float(os.environ.get("NBA_PROMOTE_HIST_K", 2.0))   # formula counted as this many games
# Health (2026-11-18). On 11/06 to 11/17, players listed day-to-day who played got 77% of their usual
# minutes (20 games); players in their first game back after missing 1 to 3 got about 93% (115).
GTD_MIN = float(os.environ.get("NBA_GTD_MIN", 1.0))   # off: 0.85 helped minutes but not points on only 16 games; retry with more
RETURN_MIN = float(os.environ.get("NBA_RETURN_MIN", 0.93))   # ON: floors for those 92 players 79% -> 84% on the replay
# Streaks (display only, 2026-11-19): the highest ladder line a player has reached in every one of
# his last STREAK_MIN+ games. On this season's box scores, with the same rate before those games,
# a player on a streak cleared the line next time far more often (83% vs 66% for players who had
# cleared it 70 to 85% of the time before). Streaks of 10+ were cleared 89% of the time.
STREAK_MIN = 5
STREAK_REL = 0.5   # listed only when the line is at least half his season average (10+ for a 28-point scorer says little)
STREAK_LADDER = {"PTS": [10, 15, 20, 25, 30, 35, 40], "REB": [4, 6, 8, 10, 12, 14],
                 "AST": [3, 4, 6, 8, 10, 12], "3PM": [1, 2, 3, 4, 5]}
# Referee crews (display only, 2026-11-19): tonight's crew from data/refs/nba, and how many free throws
# each referee's games have averaged this season (data/refs/espn + teamstats). A crew average is shown
# only when every referee has at least REF_MIN_GAMES games.
REF_MIN_GAMES = 5
# Leans to watch (display only, 2026-11-19). Found on 11/13 to 11/18 by testing about 15 situations,
# so these are being tracked, not trusted: starters projected under LEAN_FILL_MIN minutes (usually
# fill-ins) went over their line 57% of the time (294 lines), starters in games with a blowout chance
# of LEAN_BLOWOUT or more went under 56% (290). A starter who fits both is left out.
LEAN_FILL_MIN, LEAN_BLOWOUT, LEAN_FROM = 26.0, 0.30, "2026-11-19"
PROMOTE_A, PROMOTE_B = 17.7, 0.44   # fill-in starter minutes = A + B x usual (fit before 2026-11-12)
MIN_FILL_ROOM = float(os.environ.get("NBA_MIN_FILL_ROOM", 38.0))   # minutes where a player has no room left
MIN_FILL_K = float(os.environ.get("NBA_MIN_FILL_K", 1.0))         # share of the freed minutes handed out

# ============================================================== MODEL (fixed)
SD = 15.0          # spread of final margin around the point spread
                   # (13.0 until 2026-11-11; 159 games this season fit 14.3 to 16)
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
    # used by the simulation, so by every floor. Deliberately cautious: see PROJ_CUT_30.
    if mpg >= 30: return mpg * 0.80
    if mpg >= 24: return mpg * 0.90
    return mpg

# Share of his usual minutes a 30+ minute player keeps in a blowout, for the projected
# numbers only (expected, normal game, blowout game). Measured at 0.86 to 0.88 on
# 2026-11-12 (123 graded and 220 season player-games). Floors keep the 0.80 above:
# with 0.87 in the simulation, star blowout floors held 71% instead of 80% on the replay.
PROJ_CUT_30 = 0.87

def projected_blowout_minutes(mpg):
    return mpg * PROJ_CUT_30 if mpg >= 30 else blowout_minutes(mpg)

def p20(values):
    v = sorted(values)
    k = 0.2 * (len(v) - 1)
    lo = int(math.floor(k)); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)

def project(per_game, mpg, m, pace_factor, pb, stat, bump=1.0, log_rates=None, recent_rate=None, recent_min=None,
            min_scale=1.0):
    rate = blend(per_game / mpg, recent_rate)
    minutes = blend(mpg, recent_min)
    if min_scale > 1.0:
        minutes = max(minutes, min(minutes * min_scale, MIN_FILL_CAP))
    elif min_scale < 1.0:
        minutes *= min_scale
    mult = m * pace_factor * bump
    bmin = projected_blowout_minutes(minutes)
    normal = rate * minutes * mult
    blow = rate * bmin * mult
    expected = (1 - pb) * normal + pb * blow
    if log_rates is not None and len(log_rates) >= MIN_LOG_GAMES:
        floor, source = math.floor(p20(log_rates) * bmin * mult), 'log'
    else:
        floor, source = math.floor(blow * FLOOR[stat]), 'flat'
    return round(normal, 1), round(blow, 1), round(expected, 1), floor, source, round(minutes, 1)

# What a player keeps when his team LOSES by 20 or more, against a close game: share of his
# minutes, and his per-minute production. Measured on 32,022 player-games from 2024-25 and
# 2025-26, by his usual minutes. (In blowout wins players lose minutes but produce more per
# minute, so their totals barely drop: stars kept 93 to 98% of their points.)
LOSS_MIN = {"30+": 0.862, "24-30": 0.915, "15-24": 1.023}
LOSS_RATE = {"30+":   {"PTS": 0.880, "REB": 0.922, "AST": 0.888, "3PM": 0.848},
             "24-30": {"PTS": 0.940, "REB": 0.909, "AST": 0.904, "3PM": 0.889},
             "15-24": {"PTS": 0.968, "REB": 0.918, "AST": 1.000, "3PM": 0.915}}

def min_bucket(mpg):
    return "30+" if mpg >= 30 else ("24-30" if mpg >= 24 else "15-24")

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

def ladder_streak(games, s):
    """Highest ladder line reached in each of the last STREAK_MIN+ games: (line, streak length)."""
    vals = [g[s] for g in games]
    best = None
    for x in STREAK_LADDER[s]:
        k = 0
        for v in reversed(vals):
            if v < x:
                break
            k += 1
        if k >= STREAK_MIN:
            best = (x, k)
    return best


def ref_key(name):
    return re.sub(r"[^a-z]", "", (name or "").lower())     # "J.B. DeRosa" and "JB DeRosa" match


def ref_games(hist, name):
    """His games by exact name, else by last name and first initial when only one referee fits
    (ESPN has "Kladji Mulla" where the NBA has "Klajdi Mulla")."""
    k = ref_key(name)
    if k in hist:
        return hist[k]
    parts = (name or "").split()
    if len(parts) < 2:
        return []
    last, first = ref_key(parts[-1]), ref_key(parts[0])[:1]
    fits = [v for key, v in hist.items() if key.endswith(last) and key[:1] == first]
    return fits[0] if len(fits) == 1 else []


def load_crews(data, date):
    """Tonight's crews by game id (data/refs/nba/<date>.csv), or {} before the page is posted."""
    out = {}
    for r in read_csv(data / "refs" / "nba" / f"{date}.csv"):
        names = [r.get(k) for k in ("crew_chief", "referee", "umpire") if r.get(k)]
        if names:
            out[str(r.get("game_id") or "")] = names
            out[(r.get("away"), r.get("home"))] = names
    return out


def ref_history(data, before):
    """Free throws per game (both teams) in each referee's games before this date, and the league average."""
    hist, allg = defaultdict(list), []
    for path in sorted((data / "refs" / "espn").glob("*.csv")):
        d = dt.date.fromisoformat(path.stem)
        if d >= before:
            continue
        fta = defaultdict(float)
        for r in read_csv(data / "teamstats" / f"{path.stem}.csv"):
            fta[str(r["game_id"])] += fnum(r.get("FTA"), 0.0)
        for r in read_csv(path):
            g = fta.get(str(r["game_id"]))
            if not g:
                continue
            allg.append(g)
            for k in ("ref1", "ref2", "ref3", "ref4"):
                if r.get(k):
                    hist[ref_key(r[k])].append(g)
    return hist, (sum(allg) / len(allg) if allg else None)


def lean_record(data, before):
    """How each lean has done on graded nights: before LEAN_FROM (where it was found) and since."""
    rec = {k: {"found": [0, 0], "live": [0, 0]} for k in ("fill_over", "blowout_under")}
    for path in sorted((data / "graded").glob("*.csv")):
        if path.stem >= str(before):
            continue
        for r in read_csv(path):
            line, act, mins, pb = fnum(r.get("line")), fnum(r.get("actual")), fnum(r.get("minutes")), fnum(r.get("p_blowout"))
            if r.get("played") not in ("True", "true", True) or r.get("role") != "starter" or line is None or act is None or act == line:
                continue
            a, b = mins is not None and mins < LEAN_FILL_MIN, pb is not None and pb >= LEAN_BLOWOUT
            if a == b:
                continue
            k, won = ("fill_over", act > line) if a else ("blowout_under", act < line)
            slot = rec[k]["live" if path.stem >= LEAN_FROM else "found"]
            slot[0] += 1
            slot[1] += int(won)
    return rec


def pct(sorted_vals, q):
    k = q * (len(sorted_vals) - 1)
    lo = int(math.floor(k)); hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)

def simulate_game(home_spread, players, game_index):
    rng = random.Random(SEED + game_index)
    out = {p['name']: {s: [] for s in p['stats']} for p in players}
    blow_flags = []
    margins = []        # home team's simulated final margin, one per run
    for _ in range(SIMS):
        margin = rng.gauss(-home_spread, SD)
        blow = abs(margin) >= BLOWOUT
        blow_flags.append(blow)
        margins.append(margin)
        for p in players:
            base = blowout_minutes(p['minutes']) if blow else p['minutes']
            mins = max(0.0, rng.gauss(base, p.get('min_sd', MIN_SD)))
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
    simulate_game.margins = margins     # kept on the side so the return value stays as the skill has it
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
    cols = []                      # union of keys, so rows saved by an older version still fit
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(rows)

def norm(name):
    """Same player, different spellings: drop accents, punctuation and suffixes."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z ]", "", n)
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv"))

def tag(pb):
    # cut points sit at a 5 point and a 10 point spread
    return "Low" if pb < 0.21 else ("Medium" if pb <= 0.27 else "High")


# ------------------------------------------------------------------- history

def fix_centers(players):
    """ESPN lists many centers as forwards (Wembanyama, Sabonis, Gafford and others).

    When a team's starting five has no listed center, the starting forward who rebounds and
    blocks the most per minute is the one playing center. A forward who fills that spot in
    at least 60% of his starts, and at least 5 times, is treated as a center everywhere."""
    def listed(p):
        return max(("G", "F", "C"), key=lambda k: sum(1 for g in p["games"] if g["pos"] == k))
    def big(p):
        mins = sum(g["MIN"] for g in p["games"])
        return (sum(g["REB"] for g in p["games"]) + 2 * sum(g["BLK"] for g in p["games"])) / mins if mins else 0.0
    pos = {pid: listed(p) for pid, p in players.items() if p["games"]}
    lineups = defaultdict(list)
    for pid, p in players.items():
        for g in p["games"]:
            if g["starter"]:
                lineups[(g["gid"], g["team"])].append(pid)
    at_five = defaultdict(int)
    for five in lineups.values():
        if any(pos[x] == "C" for x in five):
            continue
        forwards = [x for x in five if pos[x] == "F"]
        if forwards:
            at_five[max(forwards, key=lambda x: big(players[x]))] += 1
    fixed = []
    for pid, n in at_five.items():
        starts = sum(1 for g in players[pid]["games"] if g["starter"])
        if n >= 5 and n >= 0.6 * starts:
            for g in players[pid]["games"]:
                g["pos"] = "C"
            players[pid]["center_fix"] = True
            fixed.append(players[pid]["name"])
    return fixed


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
            g = {"date": d, "team": r["team"], "MIN": mins, "gid": r["game_id"],
                 "opp": opp_of.get((r["game_id"], r["team"])),
                 "PTS": fnum(r.get("PTS"), 0.0), "REB": fnum(r.get("REB"), 0.0),
                 "AST": fnum(r.get("AST"), 0.0), "3PM": made(r.get("3PT")),
                 "FTM": made(r.get("FT")),
                 "STL": fnum(r.get("STL"), 0.0), "BLK": fnum(r.get("BLK"), 0.0),
                 "starter": str(r.get("starter", "")).lower() == "true",
                 "pos": (r.get("pos") or "F")[-1] if (r.get("pos") or "") not in ("G", "F", "C") else r.get("pos")}
            p = players[r["player_id"]]
            p["name"] = r["player"]
            p["games"].append(g)
    fix_centers(players)        # before the defense-by-position tables are built
    for p in players.values():
        for g in p["games"]:
            if g["opp"]:
                for s in STATS:
                    allowed_pos[g["opp"]][g["gid"]][(g["pos"], s)] += g[s]
    return players, team_games, allowed_pos


def team_tables(team_games, allowed_pos):
    """Per-team defense and pace, each already divided by league average."""
    def poss(r):
        v = [fnum(r.get(k)) for k in ("FGA", "OREB", "TOV", "FTA")]
        return None if None in v else v[0] - v[1] + v[2] + 0.44 * v[3]

    by_game = {(r["game_id"], r["team"]): r for rows in team_games.values() for r in rows}
    raw = {}
    for team, rows in team_games.items():
        allow = defaultdict(list); pace = []; pf = 0.0; pa = 0.0
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
                pf += fnum(r.get("PTS"), 0.0); pa += fnum(o.get("PTS"), 0.0)
        raw[team] = {"games": len(rows),
                     "allow": {s: statistics.mean(v) for s, v in allow.items() if v},
                     "pace": statistics.mean(pace) if pace else None,
                     "off": pf / sum(pace) if pace else None,      # points per possession
                     "def": pa / sum(pace) if pace else None}
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
    offs = [t["off"] for t in raw.values() if t["off"]]
    lg["PPP"] = statistics.mean(offs) if offs else None
    return raw, lg, lg_pace, dvp


def fair_line(p):
    """Win chance as a no-fee moneyline."""
    p = max(0.01, min(0.99, p))
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def team_absences(team, by_team, out_ids, gtd_ids, team_games, date):
    """Scoring a team is missing tonight: rotation players who are Out or have not played lately.

    A player's edge is what he scores beyond an average teammate in the same minutes.
    It is scaled by the share of team games he played, because the team's season
    numbers already include the games he missed."""
    rows = team_games.get(team, [])
    days = sorted({r["_date"] for r in rows})
    if not days:
        return 0.0, []
    cutoff = days[-4:][0]
    ppm = statistics.mean(fnum(r["PTS"], 0.0) for r in rows) / 240.0
    lost, names = 0.0, []
    for pid, pr in by_team.get(team, []):
        missing = pid in out_ids or (pr["last_date"] < cutoff and pid not in gtd_ids)
        if not missing or pr["gp"] < 3 or pr["mpg"] < 15:
            continue
        edge = max(0.0, pr["PTS"] - pr["mpg"] * ppm) * min(1.0, pr["gp"] / len(days))
        if edge > 0:
            lost += edge
            names.append(pr["name"])
    return lost, names


# Absences that change the OTHER team's night. Measured on 2024-25 and 2025-26, each team
# against itself: steals leader out -> opponent +1.6 points; top rebounder out -> opponent
# +1.8 rebounds and +2.2 paint points; shot blocker out -> opponent +1.8 paint points; lead
# playmaker out -> about one fewer possession for both teams. Notes only: no number changes.
KEY_ROLES = (("rebounder", "top rebounder", lambda pr: pr["REB"] >= 9 and pr["mpg"] >= 26),
             ("blocker", "shot blocker", lambda pr: pr["BLK"] >= 1.4 and pr["mpg"] >= 24),
             ("stealer", "steals leader", lambda pr: pr["STL"] >= 1.5 and pr["mpg"] >= 26),
             ("playmaker", "lead playmaker", lambda pr: pr["AST"] >= 7 and pr["mpg"] >= 28))


def key_absences(team, by_team, out_ids, gtd_ids, team_games):
    days = sorted({r["_date"] for r in team_games.get(team, [])})
    if not days:
        return []
    cutoff = days[-4:][0]
    out = []
    for pid, pr in by_team.get(team, []):
        missing = pid in out_ids or (pr["last_date"] < cutoff and pid not in gtd_ids)
        if not missing or pr["gp"] < 5:
            continue
        for key, label, test in KEY_ROLES:
            if test(pr):
                out.append({"role": key, "label": label, "name": pr["name"]})
    return out


def on_back_to_back(team, team_games, date):
    return any(r["_date"] == date - dt.timedelta(days=1) for r in team_games.get(team, []))


def load_prior(data):
    """Last season's per-minute rates, minutes and team scoring, or empty if switched off."""
    if not USE_PRIOR:
        return {}, {}
    players = {}
    for r in read_csv(data / "prior" / f"players_{PRIOR_SEASON}.csv"):
        m, gp = fnum(r["minutes"], 0.0), fnum(r["gp"], 0.0)
        if m >= 300 and gp >= 1:
            players[r["player_id"]] = {"gp": gp, "mpg": m / gp,
                                       "rate": {"PTS": fnum(r["pts"], 0.0) / m, "REB": fnum(r["reb"], 0.0) / m,
                                                "AST": fnum(r["ast"], 0.0) / m, "3PM": fnum(r["tpm"], 0.0) / m}}
    t = read_csv(data / "prior" / f"teams_{PRIOR_SEASON}.csv")
    teams = {}
    if t:
        mf = statistics.mean(fnum(r["pts_for"]) for r in t); ma = statistics.mean(fnum(r["pts_against"]) for r in t)
        teams = {r["team"]: {"off": fnum(r["pts_for"]) / mf, "def": fnum(r["pts_against"]) / ma} for r in t}
    return players, teams


def game_prediction(home, away, raw, lg, lg_pace, spread, total, home_minus=0.0, away_minus=0.0, prior=None):
    """Projected score and win chance from team scoring and defense per possession."""
    h, a, L = raw.get(home), raw.get(away), lg.get("PPP")
    if not h or not a or not L or not lg_pace or not all((h["off"], h["def"], a["off"], a["def"], h["pace"], a["pace"])):
        return None
    def r(t, k, avg):
        return avg + (t[k] - avg) * t["games"] / (t["games"] + RATE_K)
    poss = r(h, "pace", lg_pace) * r(a, "pace", lg_pace) / lg_pace
    hp = poss * r(h, "off", L) * r(a, "def", L) / L + HOME_EDGE / 2 - home_minus
    ap = poss * r(a, "off", L) * r(h, "def", L) / L - HOME_EDGE / 2 - away_minus
    if prior and home in prior and away in prior:
        # the margin leans on last season's team strength; the total stays on this season's scoring
        def rp(team, t, k):
            return (t[k] * t["games"] + PRIOR_TEAM_K * L * prior[team][k]) / (t["games"] + PRIOR_TEAM_K)
        m2 = (poss * rp(home, h, "off") * rp(away, a, "def") / L + HOME_EDGE / 2 - home_minus) \
            - (poss * rp(away, a, "off") * rp(home, h, "def") / L - HOME_EDGE / 2 - away_minus)
        tot = hp + ap
        hp, ap = (tot + m2) / 2, (tot - m2) / 2
    pw = phi((hp - ap) / SD)
    out = {"home_pts": round(hp, 1), "away_pts": round(ap, 1), "margin": round(hp - ap, 1),
           "total": round(hp + ap, 1), "home_win": round(pw, 3),
           "home_ml": fair_line(pw), "away_ml": fair_line(1 - pw),
           "market_home_win": round(phi(-spread / SD), 3) if spread is not None else None,
           "market_home_pts": None, "market_away_pts": None}
    if spread is not None and total is not None:
        out["market_home_pts"] = round((total - spread) / 2, 1)
        out["market_away_pts"] = round((total + spread) / 2, 1)
    return out


def player_profile(p):
    g = p["games"]
    n = len(g)
    mpg = sum(x["MIN"] for x in g) / n
    prof = {"name": p["name"], "gp": n, "mpg": mpg, "team": g[-1]["team"],
            "pos": max(("G", "F", "C"), key=lambda k: sum(1 for x in g if x["pos"] == k)),
            "last_date": g[-1]["date"],
            "start_share": sum(1 for x in g[-5:] if x["starter"]) / len(g[-5:]),
            "FTM": sum(x["FTM"] for x in g) / n,
            "STL": sum(x["STL"] for x in g) / n, "BLK": sum(x["BLK"] for x in g) / n}
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

def run_project(date, data, docs, now=None, lock=True):
    slate = read_csv(data / "slate" / f"{date}.csv")
    if not slate:
        print(f"no games found for {date}; nothing to project")
        return
    odds = {r["game_id"]: r for r in read_csv(data / "odds" / f"{date}.csv")}
    inj = read_csv(data / "injuries" / f"{date}.csv")
    # Only these statuses mean "might play". Anything else on the report (Out, Suspension,
    # and any status not seen before) is treated as not playing.
    maybe = ("day-to-day", "questionable", "probable", "game time decision", "gtd")
    gtd_ids = {r["player_id"] for r in inj if (r.get("status") or "").strip().lower() in maybe}
    out_ids = {r["player_id"] for r in inj} - gtd_ids
    lines = {}      # prop lines, matched by ESPN player id when the file has one, by name otherwise
    for r in read_csv(data / "props" / f"{date}.csv"):
        v = fnum(r.get("line"))
        if v is None:
            continue
        if r.get("player_id"):
            lines[(r["player_id"], r["stat"])] = v
        if r.get("player"):
            lines[(norm(r["player"]), r["stat"])] = v

    players, team_games, allowed_pos = load_history(data, date)
    raw, lg, lg_pace, dvp = team_tables(team_games, allowed_pos)
    profs = {pid: player_profile(p) for pid, p in players.items() if p["games"]}
    prior_players, prior_teams = load_prior(data)
    for pid, pr in profs.items():       # "a_" values are what the projection uses; raw season averages stay as they are
        pri = prior_players.get(pid)
        pr["a_mpg"] = ((pr["mpg"] * pr["gp"] + PRIOR_KG * pri["mpg"]) / (pr["gp"] + PRIOR_KG)
                       if pri and pri["gp"] >= 20 else pr["mpg"])
        for s in STATS:
            rate = pr[s] / pr["mpg"]
            if pri:
                rate = (pr[s] * pr["gp"] + PRIOR_KMIN * pri["rate"][s]) / (pr["mpg"] * pr["gp"] + PRIOR_KMIN)
            pr["a_" + s] = rate * pr["a_mpg"]
    by_team = defaultdict(list)
    for pid, pr in profs.items():
        by_team[pr["team"]].append((pid, pr))

    promo_hist = {}      # player -> his minutes in earlier starts while tonight's missing starter sat

    def health_mult(pid, pr, team):
        """Fewer minutes for a player listed day-to-day, or in his first game back after missing a few."""
        f = 1.0
        if pid in gtd_ids:
            f *= GTD_MIN
        days = sorted({r["_date"] for r in team_games.get(team, [])})
        missed = sum(1 for d_ in days if d_ > pr["last_date"])
        if 1 <= missed <= 3:
            f *= RETURN_MIN
        return f

    def available(team):
        recent_dates = sorted({r["_date"] for r in team_games.get(team, [])})[-4:]
        cutoff = recent_dates[0] if recent_dates else date
        cands = []
        for pid, pr in by_team.get(team, []):
            if pid in out_ids:
                continue
            if pr["last_date"] < cutoff and pid not in gtd_ids:
                continue          # has not played lately and is not on the report
            cands.append((pid, pr))
        return cands

    def min_scale(team, starters=()):
        """Per player: how much to stretch his minutes to cover teammates ruled out tonight."""
        if MIN_FILL == "off":
            return {}
        if MIN_FILL in ("promote", "promote+"):
            return promote_scale(team, starters)
        cands = available(team)
        usual = {pid: blend(pr["a_mpg"], pr["recent_min"]) for pid, pr in cands}
        have = sum(usual.values())
        if not have:
            return {}
        if MIN_FILL == "total":
            f = min(MIN_FILL_MAX, max(1.0, MIN_FILL_TARGET / have))
            return {pid: f for pid in usual}
        # the minutes of players ruled out who were still in the rotation in the team's last
        # 4 games; a longer absence is already in his teammates' recent minutes
        days = sorted({r["_date"] for r in team_games.get(team, [])})[-4:]
        cutoff = days[0] if days else date
        freed = MIN_FILL_K * sum(blend(pr["a_mpg"], pr["recent_min"]) for pid, pr in by_team.get(team, [])
                                 if pid in out_ids and pr["last_date"] >= cutoff and pr["gp"] >= 3)
        if not freed:
            return {}
        if MIN_FILL == "even":
            f = min(MIN_FILL_MAX, (have + freed) / have)
            return {pid: f for pid in usual}
        # "on": shared by room to grow, so a 20-minute player takes far more than a 35-minute star
        room = {pid: m * max(0.0, MIN_FILL_ROOM - m) for pid, m in usual.items()}
        tot = sum(room.values())
        if not tot:
            return {}
        return {pid: min(MIN_FILL_MAX, (m + freed * room[pid] / tot) / m) if m else 1.0
                for pid, m in usual.items()}

    def promote_scale(team, starters):
        """A player moved into the starting five takes most of the missing starter's minutes:
        PROMOTE_A + PROMOTE_B x his usual minutes (fit on 148 promotions before 2026-11-12).
        "promote+" also shares what the missing players leave beyond that by room to grow."""
        usual = {pid: blend(pr["a_mpg"], pr["recent_min"]) for pid, pr in available(team)}
        out = {}
        gained = 0.0
        for pid, pr in starters:
            m = usual.get(pid)
            if pr["start_share"] < 0.5 and m:
                new = PROMOTE_A + PROMOTE_B * m
                h = promo_hist.get(pid) if PROMOTE_HIST == "on" else None
                if h:   # his own minutes as a fill-in starter, trusted more as the games add up
                    new = (sum(h) + PROMOTE_HIST_K * new) / (len(h) + PROMOTE_HIST_K)
                new = min(MIN_FILL_CAP, max(m, new))
                out[pid] = new / m
                gained += new - m
        if MIN_FILL == "promote+":
            days = sorted({r["_date"] for r in team_games.get(team, [])})[-4:]
            cutoff = days[0] if days else date
            freed = MIN_FILL_K * sum(blend(pr["a_mpg"], pr["recent_min"]) for pid, pr in by_team.get(team, [])
                                     if pid in out_ids and pr["last_date"] >= cutoff and pr["gp"] >= 3)
            left = max(0.0, freed - gained)
            room = {pid: m * max(0.0, MIN_FILL_ROOM - m) for pid, m in usual.items() if pid not in out}
            tot = sum(room.values())
            if left and tot:
                for pid, r in room.items():
                    m = usual[pid]
                    out[pid] = min(MIN_FILL_MAX, (m + left * r / tot) / m) if m else 1.0
        return out

    def pool(team):
        cands = available(team)
        starters = sorted([c for c in cands if c[1]["start_share"] >= 0.5],
                          key=lambda c: (-c[1]["start_share"], -c[1]["mpg"]))[:5]
        sid = {c[0] for c in starters}
        if len(starters) < 5:      # fill open spots with the heaviest-minute players left
            rest = sorted([c for c in cands if c[0] not in sid and c[1]["gp"] >= 3],
                          key=lambda c: (-c[1]["start_share"], -c[1]["recent_min"] if c[1]["recent_min"] else -c[1]["mpg"]))
            if PROMOTE_POS == "on":
                # like for like: each open spot goes first to a player at the missing starter's position
                days = sorted({r["_date"] for r in team_games.get(team, [])})[-4:]
                cut = days[0] if days else date
                gone = sorted([(pid, pr) for pid, pr in by_team.get(team, [])
                               if pid in out_ids and pr["start_share"] >= 0.5 and pr["last_date"] >= cut],
                              key=lambda c: -c[1]["mpg"])
                all_days = {r["_date"] for r in team_games.get(team, [])}
                for gid_, g in gone[:5 - len(starters)]:
                    pick = None
                    if PROMOTE_HIST == "on":
                        # who started when this player sat out earlier this season
                        away = all_days - {x["date"] for x in players[gid_]["games"] if x["team"] == team}
                        best, best_n = None, 0
                        for c in rest:
                            if c[0] in sid:
                                continue
                            mins = [x["MIN"] for x in players[c[0]]["games"]
                                    if x["team"] == team and x["starter"] and x["date"] in away]
                            if len(mins) > best_n:
                                best, best_n = c, len(mins)
                                promo_hist[c[0]] = mins
                        pick = best
                    if pick is None:
                        pick = next((c for c in rest if c[1]["pos"] == g["pos"] and c[0] not in sid), None)
                    if pick:
                        starters.append(pick); sid.add(pick[0])
                rest = [c for c in rest if c[0] not in sid]
            starters += rest[:5 - len(starters)]
            sid = {c[0] for c in starters}
        bench = sorted([c for c in cands if c[0] not in sid and c[1]["mpg"] >= BENCH_MIN and c[1]["gp"] >= 3],
                       key=lambda c: -c[1]["mpg"])
        return starters, bench

    def out_scorers(team):
        """Scorers this team is missing tonight: on the report as Out, or not seen lately."""
        days = sorted({r["_date"] for r in team_games.get(team, [])})
        cutoff = days[-4:][0] if days else date
        trigger = BUMP_PPG if BUMP_MODE == "flat" else BUMP_TRIGGER
        res = []
        for pid, pr in by_team.get(team, []):
            missing = pid in out_ids or (BUMP_MODE != "flat" and pr["last_date"] < cutoff and pid not in gtd_ids)
            if missing and pr["PTS"] >= trigger and pr["gp"] >= 3:
                share = min(1.0, pr["gp"] / max(1, len(days)))
                res.append((pid, pr, share))
        return res

    def teammate_bump(pid, team, outs, stat):
        """How this player's per-minute rate changes without the missing teammates.

        Compared with his season rate, which already includes any games the teammate
        missed, so a long absence is not counted twice. With few such games the number
        is pulled toward a small default lift."""
        if BUMP_MODE == "flat":
            return min(1.10, 1.0 + 0.05 * len(outs))
        mine = [g for g in players[pid]["games"] if g["MIN"] >= 15 and g["team"] == team]
        tot_min = sum(g["MIN"] for g in mine)
        base = sum(g[stat] for g in mine) / tot_min if tot_min else 0.0
        b = 1.0
        for opid, opr, share in outs:
            prior = 1.0 + (0.05 if opr["PTS"] >= BUMP_PPG else 0.03) * share
            seen = {g["date"] for g in players[opid]["games"]}
            wo = [g for g in mine if g["date"] not in seen]
            wmin = sum(g["MIN"] for g in wo)
            # points only: assists without a teammate were too noisy to beat the default on the replay
            if stat == "PTS" and len(mine) >= 5 and wo and wmin and base > 0:
                ratio = (sum(g[stat] for g in wo) / wmin) / base
                b *= prior + (ratio - prior) * len(wo) / (len(wo) + BUMP_SHRINK)
            else:
                b *= prior
        return max(0.90, min(1.25, b))

    games_out, proj_rows, notes, pred_rows = [], [], [], []
    slate = sorted(slate, key=lambda r: (r["date"], r["game_id"]))

    # Lock at tip: a game that has started keeps the numbers from the last run before it tipped.
    now = now or dt.datetime.now(dt.timezone.utc)
    old_games, old_rows, old_preds = {}, defaultdict(list), {}
    prev = docs / "data" / f"{date}.json"
    if lock and prev.exists():
        try:
            old_games = {g["game_id"]: g for g in json.loads(prev.read_text())["games"]}
        except (ValueError, KeyError):
            old_games = {}
        for r in read_csv(data / "projections" / f"{date}.csv"):
            old_rows[r["game_id"]].append(r)
        old_preds = {r["game_id"]: r for r in read_csv(data / "gamepreds" / f"{date}.csv")}

    def dvp_block(opp):
        """What this defense has allowed to each position so far, against the league average (raw)."""
        return {pos: {s: round(dvp.get(opp, {}).get((pos, s), 1.0), 3) for s in STATS} for pos in ("G", "F", "C")}

    def tip_of(g):
        return dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))

    for gi, g in enumerate(slate):
        home, away, gid = g["home"], g["away"], g["game_id"]
        started = lock and tip_of(g) <= now
        if started and gid in old_games and old_rows.get(gid):
            kept = old_games[gid]
            kept["locked"] = True
            if not kept.get("pred"):     # saved before game predictions existed; uses pre-date history only
                kept["pred"] = game_prediction(home, away, raw, lg, lg_pace, kept.get("spread"), kept.get("total"),
                                               prior=prior_teams)
                if kept["pred"]:
                    old_preds[gid] = dict({"date": str(date), "game_id": gid, "home": home, "away": away,
                                           "spread": kept.get("spread"), "market_total": kept.get("total")}, **kept["pred"])
            for tb in kept.get("teams", []):   # descriptive only; saved numbers are not touched
                if "dvp" not in tb:
                    tb["dvp"] = dvp_block(tb["opp"])
                    tb["opp_games"] = raw.get(tb["opp"], {}).get("games", 0)
            games_out.append(kept)
            proj_rows.extend(old_rows[gid])
            if gid in old_preds:
                pred_rows.append(old_preds[gid])
            continue
        if started:
            notes.append(f"{away} at {home}: already under way at run time with no earlier run saved, so this is not a pregame number.")
        o = odds.get(gid, {})
        spread, total = fnum(o.get("spread")), fnum(o.get("over_under"))
        adj = {}
        for t in (home, away):
            lost, names = team_absences(t, by_team, out_ids, gtd_ids, team_games, date)
            b2b = on_back_to_back(t, team_games, date)
            adj[t] = {"missing": names, "b2b": b2b, "minus": round(INJ_K * lost + (B2B_PTS if b2b else 0.0), 1),
                      "key_out": key_absences(t, by_team, out_ids, gtd_ids, team_games)}
        pred = game_prediction(home, away, raw, lg, lg_pace, spread, total, adj[home]["minus"], adj[away]["minus"],
                               prior=prior_teams)
        if pred:
            pred["home_adj"], pred["away_adj"] = adj[home], adj[away]
        # the spread sets blowout risk; with no spread posted, the model's own margin stands in
        eff_spread = spread if spread is not None else (-pred["margin"] if pred else 0.0)
        if spread is None:
            notes.append(f"{away} at {home}: no spread posted at fetch time, so blowout risk uses "
                         + (f"the model margin ({home} {pred['margin']:+.1f})." if pred else "an even game."))
        pb = p_blowout(eff_spread)
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
            starters, bench = pool(team)
            fill = min_scale(team, starters)
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
                        if s == "3PM" and TPM_MATCHUP != "full":
                            m = 1.0 if TPM_MATCHUP == "none" else matchup(s, f, od["games"], None)
                        bump = teammate_bump(pid, team, outs, s) if (outs and s in ("PTS", "AST")) else 1.0
                        lr = pr["log_rates"][s] or None
                        rr = pr["recent_rate"][s] if pr["recent_rate"] else None
                        normal, blow, expected, rfloor, src, minutes = project(
                            pr["a_" + s], pr["a_mpg"], m, pace_factor, pb, s, bump, lr, rr, pr["recent_min"], fill.get(pid, 1.0) * health_mult(pid, pr, team))
                        entry["min"] = minutes
                        entry["stats"][s] = {"normal": normal, "blowout": blow, "expected": expected,
                                             "rule_floor": rfloor, "floor_source": src,
                                             "matchup": round(m, 3), "bump": round(bump, 3),
                                             "dvp": round(f, 3), "base_rate": round(pr[s] / pr["mpg"], 5),
                                             "season_avg": round(pr[s], 2),
                                             "line": lines.get((pid, s), lines.get((norm(pr["name"]), s)))}
                        sim_stats[s] = {"rate": blend(pr["a_" + s] / pr["a_mpg"], rr), "mult": m * pace_factor * bump,
                                        "log_rates": lr}
                    sim_players.append({"name": pid, "minutes": entry["min"], "stats": sim_stats,
                                        "min_sd": MIN_SD_BENCH if role == "bench" else (MIN_SD if entry["star"] else MIN_SD_STARTER)})
                    rows.append(entry)
            team_blocks.append({"team": team, "opp": opp, "area": {k: round(v, 3) for k, v in area.items()},
                                "out_scorers": [o[1]["name"] for o in outs], "min_fill": {profs[k]["name"]: round(v, 3) for k, v in fill.items() if v > 1.0}, "b2b": adj[team]["b2b"],
                                "dvp": dvp_block(opp), "opp_games": od["games"],
                                # what the other team is missing tonight, and whether it is the tired one
                                "opp_missing": adj[opp]["key_out"],
                                "opp_tired": bool(adj[opp]["b2b"] and not adj[team]["b2b"]), "players": rows})

        sims, flags = simulate_game(eff_spread, sim_players, gi)
        for tb in team_blocks:
            for e in tb["players"]:
                for s in STATS:
                    st = e["stats"][s]
                    vals = sims[e["id"]][s]
                    if LINE_W < 1.0 and st["line"] is not None and st["expected"] > 0:
                        target = LINE_W * st["expected"] + (1 - LINE_W) * st["line"]
                        k = max(0.6, min(1.6, target / st["expected"]))
                        vals = [int(v * k + 0.5) for v in vals]
                        sims[e["id"]][s] = vals
                        st["model_expected"] = st["expected"]
                        st["expected"] = round(st["expected"] * k, 1)
                        st["normal"], st["blowout"] = round(st["normal"] * k, 1), round(st["blowout"] * k, 1)
                    res = summarize(vals, flags, st["line"])
                    if P_OVER_CAL == "on" and res["p_over"] is not None:
                        st["sim_p_over"] = res["p_over"]
                        res["p_over"] = round(min(0.95, max(0.05, 0.495 + 0.25 * (res["p_over"] - 0.45))), 3)
                    if s == "PTS" and e["role"] == "bench" and FLOOR_Q_BENCH_PTS != 0.20:
                        res["floor"] = int(pct(sorted(vals), FLOOR_Q_BENCH_PTS))
                        bv = sorted(v for v, b in zip(vals, flags) if b)
                        if len(bv) >= 200:
                            res["blowout_floor"] = int(pct(bv, FLOOR_Q_BENCH_PTS))
                    # Ceiling: the number he reaches in his best 1 simulated game in 20 (CEIL_Q). Display only.
                    st["ceiling"] = int(pct(sorted(vals), CEIL_Q))
                    # Blown-out floor: the number reached in 80% of the simulated games his team LOST by 20+,
                    # with the measured drop in minutes and per-minute production applied. Display only:
                    # it does not change any other number.
                    if e["min"]:
                        b_ = min_bucket(e["min"]); is_home = e["team"] == home
                        k_ = LOSS_RATE[b_][s] * LOSS_MIN[b_] / (blowout_minutes(e["min"]) / e["min"])
                        lv = sorted(v * k_ for v, m_ in zip(vals, simulate_game.margins)
                                    if (m_ <= -BLOWOUT if is_home else m_ >= BLOWOUT))
                        st["loss_floor"] = min(int(pct(lv, 0.20)), res["floor"]) if len(lv) >= 100 else None
                    else:
                        st["loss_floor"] = None
                    sk = ladder_streak(players[e["id"]]["games"], s)
                    st["streak"] = ({"line": sk[0], "games": sk[1],
                                     "model": round(sum(1 for v in vals if v >= sk[0]) / len(vals), 3),
                                     "last5": [g[s] for g in players[e["id"]]["games"][-5:]]} if sk else None)
                    if s == "3PM":      # a floor of 0 says little, so threes also get "at least" chances
                        st["at_least"] = {str(k): round(sum(1 for v in vals if v >= k) / len(vals), 3) for k in (1, 2, 3)}
                    # whole-number rounding can push a tiny floor above the expected value
                    res["floor"] = min(res["floor"], int(st["expected"]), int(FLOOR_CAP[s] * st["expected"]))
                    if res["blowout_floor"] is not None:
                        res["blowout_floor"] = min(res["blowout_floor"], res["floor"])
                    st.update(floor=res["floor"], blowout_floor=res["blowout_floor"],
                              p_over=res["p_over"], sim_mean=res["sim_mean"])
                    st["gap"] = (res["floor"] - st["line"]) if st["line"] is not None else None
                    # 20% away from the line, and at least 1.5 in absolute terms so small numbers do not all flag
                    st["check"] = bool(st["line"] and abs(st["expected"] - st["line"]) / st["line"] >= 0.20
                                       and abs(st["expected"] - st["line"]) >= 1.5)
                    if st["expected"] >= 5 and abs(res["sim_mean"] - st["expected"]) / st["expected"] > 0.05:
                        notes.append(f"{e['name']} {s}: simulation average {res['sim_mean']} vs expected {st['expected']}.")
                    proj_rows.append({
                        "date": str(date), "game_id": gid, "player_id": e["id"], "player": e["name"],
                        "team": e["team"], "opp": e["opp"], "role": e["role"], "star": e["star"], "stat": s,
                        "minutes": e["min"], "normal": st["normal"], "blowout": st["blowout"],
                        "expected": st["expected"], "floor": st["floor"], "blowout_floor": st["blowout_floor"],
                        "p_over": st["p_over"], "rule_floor": st["rule_floor"],
                        "floor_source": st["floor_source"], "line": st["line"],
                        "streak_line": st["streak"]["line"] if st["streak"] else None,
                        "streak_games": st["streak"]["games"] if st["streak"] else None,
                        "streak_model": st["streak"]["model"] if st["streak"] else None,
                        "spread": spread, "p_blowout": round(pb, 3),
                        # kept so the morning grade can check whether matchups carry over
                        "pos": e["pos"], "dvp": st["dvp"], "area3": tb["area"]["f3"], "base_rate": st["base_rate"],
                        "season_avg": st["season_avg"], "model": MODEL_VERSION, "loss_floor": st["loss_floor"],
                        "ceiling": st["ceiling"],
                        "p_ge1": st.get("at_least", {}).get("1", ""), "p_ge2": st.get("at_least", {}).get("2", ""),
                        "p_ge3": st.get("at_least", {}).get("3", "")})
        games_out.append({"game_id": gid, "home": home, "away": away, "tip": g["date"],
                          "spread": spread, "total": total, "favorite": o.get("details"),
                          "p_blowout": round(pb, 3), "tag": tag(pb), "locked": False, "pred": pred,
                          "pace": round(pace_factor, 3), "ceiling": ceil, "teams": team_blocks})
        if pred:
            pred_rows.append(dict({"date": str(date), "game_id": gid, "home": home, "away": away,
                                   "spread": spread, "market_total": total},
                                  **{k: v for k, v in pred.items() if not isinstance(v, dict)}))

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
               "floor": st["floor"], "blowout_floor": st["blowout_floor"], "loss_floor": st.get("loss_floor"),
               "expected": st["expected"]}
              for e, s, st in (with_line + no_line)[:10]]

    # Referee crews and leans to watch (display only)
    crews = load_crews(data, date)
    rhist, lg_fta = ref_history(data, date)
    leans = []
    for g in games_out:
        names = crews.get(str(g["game_id"])) or crews.get((g["away"], g["home"]))
        if names:
            per = [ref_games(rhist, n) for n in names]
            ok = all(len(x) >= REF_MIN_GAMES for x in per)
            g["refs"] = {"names": names, "league_fta": round(lg_fta, 1) if lg_fta else None,
                         "crew_fta": round(sum(sum(x) / len(x) for x in per) / len(per), 1) if ok else None,
                         "games": [len(x) for x in per]}
        for tb in g["teams"]:
            for e in tb["players"]:
                if e["role"] != "starter" or not e.get("min"):
                    continue
                a, b = e["min"] < LEAN_FILL_MIN, g["p_blowout"] >= LEAN_BLOWOUT
                if a == b:
                    continue
                for s_ in STATS:
                    st = e["stats"][s_]
                    if st.get("line") is None:
                        continue
                    leans.append({"name": e["name"], "team": e["team"], "gid": g["game_id"], "stat": s_,
                                  "line": st["line"], "expected": st["expected"], "side": "over" if a else "under",
                                  "why": f"projected {e['min']:.1f} min" if a else f"blowout chance {g['p_blowout']:.0%}"})
    leans_out = {"tonight": leans, "record": lean_record(data, date), "fill_min": LEAN_FILL_MIN,
                 "blowout": LEAN_BLOWOUT, "from": LEAN_FROM}

    # Streaks: longest first, then the higher line
    streaks = {s: sorted([{"name": e["name"], "team": e["team"], "gid": g["game_id"], "season": e["season"][s],
                           "expected": e["stats"][s]["expected"], "prop": e["stats"][s]["line"],
                           **e["stats"][s]["streak"]}
                          for g in games_out for tb in g["teams"] for e in tb["players"] if e["stats"][s].get("streak")
                          and e["stats"][s]["streak"]["line"] >= STREAK_REL * e["season"][s]],
                         key=lambda x: (-x["games"], -x["line"])) for s in STATS}

    hist_dates = sorted({r["_date"] for rows in team_games.values() for r in rows})
    n_log = sum(1 for r in proj_rows if r["floor_source"] == "log")
    now_et = dt.datetime.now(ET)
    open_tips = [tip_of(g) for g in slate if tip_of(g) > now]
    hours_early = (min(open_tips) - now).total_seconds() / 3600 if open_tips else 0
    payload = {
        "date": str(date), "run_time_et": now_et.strftime("%Y-%m-%d %I:%M %p ET"),
        "run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "model": MODEL_VERSION,
        "early_run": hours_early > 3,
        "games": games_out, "targets": targets, "safest": safest, "streaks": streaks, "leans": leans_out,
        "method": {
            "history_days": len(hist_dates),
            "history_from": str(hist_dates[0]) if hist_dates else None,
            "history_to": str(hist_dates[-1]) if hist_dates else None,
            "log_floors": n_log, "flat_floors": len(proj_rows) - n_log,
            "lines_found": sum(1 for r in proj_rows if fnum(r["line"]) is not None),
            "players": len(proj_rows) // len(STATS),
            "locked_games": sum(1 for g in games_out if g.get("locked")),
            "centers_fixed": sorted(p["name"] for p in players.values() if p.get("center_fix")),
            "sd": SD,
            "notes": notes[:40],
        },
    }
    write_csv(proj_rows, data / "projections" / f"{date}.csv")
    if pred_rows:
        write_csv(pred_rows, data / "gamepreds" / f"{date}.csv")
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
    signed = {(r["game_id"], r["team"]): fnum(r["margin"], 0) for r in teams}
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
        r["team_margin"] = signed.get((r["game_id"], r["team"]), "")      # negative = his team lost
        out.append(r)
    write_csv(out, data / "graded" / f"{date}.csv")
    return out


def left_early(r):
    """A starter who played under half his projected minutes in a game that was not a blowout.

    Usually an injury exit, sometimes fouls or an ejection. No projection can see it coming,
    so floors are reported both with and without these players."""
    mins, proj = fnum(r.get("actual_minutes")), fnum(r.get("minutes"))
    if r.get("role") != "starter":      # a bench player losing his minutes is a real miss and still counts
        return False
    return (str(r["played"]) == "True" and mins is not None and proj and mins < 0.5 * proj
            and fnum(r.get("final_margin"), 0) < BLOWOUT)


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
        cz = [r for r in q if fnum(r.get("ceiling")) is not None]
        if cz:      # a ceiling should be reached about 1 time in 10
            acc[s]["ceiling_hit"] = round(sum(f(r, "actual") >= f(r, "ceiling") for r in cz) / len(cz), 3)
            acc[s]["ceiling_n"] = len(cz)
        nv = [r for r in q if fnum(r.get("season_avg")) is not None]
        if nv:      # the simplest possible projection: his season average
            acc[s]["naive_mae"] = round(statistics.mean(abs(f(r, "actual") - f(r, "season_avg")) for r in nv), 3)
            acc[s]["model_mae_same"] = round(statistics.mean(abs(f(r, "actual") - f(r, "expected")) for r in nv), 3)
        full = [r for r in fl if not left_early(r)]
        acc[s]["floor_hit_full"] = round(sum(f(r, "actual") >= f(r, "floor") for r in full) / len(full), 3) if full else None
        for src in ("log", "flat"):
            z = [r for r in q if r["floor_source"] == src]
            acc[s][f"rule_floor_hit_{src}"] = (round(sum(f(r, "actual") >= f(r, "rule_floor") for r in z) / len(z), 3) if z else None)
            acc[s][f"rule_floor_n_{src}"] = len(z)
    res["stats"] = acc
    stars = [r for r in played if r["stat"] == "PTS" and str(r["star"]) == "True"]
    res["star_floors"] = len(stars)
    res["star_floor_hit"] = round(sum(f(r, "actual") >= f(r, "floor") for r in stars) / len(stars), 3) if stars else None
    # Blowouts split by side: stars hold up when their team wins big and struggle when it loses big.
    def held(z, key):
        z = [r for r in z if f(r, key) is not None]
        return {"n": len(z), "hit": round(sum(f(r, "actual") >= f(r, key) for r in z) / len(z), 3)} if z else None
    sm = [r for r in stars if fnum(r.get("team_margin")) is not None]
    won, lost = [r for r in sm if f(r, "team_margin") >= BLOWOUT], [r for r in sm if f(r, "team_margin") <= -BLOWOUT]
    res["star_blowout_sides"] = {"won_floor": held(won, "floor"), "lost_floor": held(lost, "floor"),
                                 "lost_blowout_floor": held(lost, "blowout_floor"),
                                 "lost_loss_floor": held([r for r in lost if r.get("loss_floor") not in (None, "", "None")], "loss_floor")}
    sfull = [r for r in stars if not left_early(r)]
    res["star_floors_full"] = len(sfull)
    res["star_floor_hit_full"] = round(sum(f(r, "actual") >= f(r, "floor") for r in sfull) / len(sfull), 3) if sfull else None
    res["left_early_n"] = len({(r["date"], r["player_id"]) for r in played if left_early(r)})
    for label, test in (("close", lambda m: m < BLOWOUT), ("blowout", lambda m: m >= BLOWOUT)):
        z = [r for r in stars if test(fnum(r["final_margin"], 0))]
        res[f"star_minutes_{label}"] = ({"n": len(z), "projected": round(statistics.mean(f(r, "minutes") for r in z), 1),
                                         "actual": round(statistics.mean(f(r, "actual_minutes") for r in z), 1)} if z else None)
    # Matchup check: did players do better against defenses that had been soft at their position?
    # Baseline is the player's own pre-game rate times the minutes he actually played.
    def carry(z, key, lo, hi):
        out = {}
        for label, test in (("tough", lambda v: v <= lo), ("middle", lambda v: lo < v < hi), ("soft", lambda v: v >= hi)):
            q = [r for r in z if test(f(r, key))]
            base = sum(f(r, "base_rate") * f(r, "actual_minutes") for r in q)
            out[label] = {"n": len(q), "ratio": round(sum(f(r, "actual") for r in q) / base, 3) if base else None}
        return out
    res["matchup_check"] = {}
    for s in STATS:
        z = [r for r in played if r["stat"] == s and fnum(r.get("dvp")) is not None and fnum(r.get("base_rate"))
             and fnum(r.get("actual_minutes"), 0) >= 15]
        if z:
            res["matchup_check"][s] = carry(z, "dvp", 0.88, 1.12)
            if s == "3PM" and all(fnum(r.get("area3")) is not None for r in z):
                res["matchup_check"]["3PM_team"] = carry(z, "area3", 0.92, 1.08)
    # Threes: do the "at least 1 / 2 / 3" chances mean what they say?
    tz = [r for r in played if r["stat"] == "3PM" and fnum(r.get("p_ge1")) is not None]
    res["threes_check"] = {}
    for k in (1, 2, 3):
        rowsk = []
        for label, lo, hi in (("under 30%", 0, .3), ("30 to 50%", .3, .5), ("50 to 70%", .5, .7), ("70 to 85%", .7, .85), ("85% and up", .85, 1.01)):
            z = [r for r in tz if lo <= f(r, f"p_ge{k}") < hi]
            if z:
                rowsk.append({"bucket": label, "n": len(z), "made": round(sum(f(r, "actual") >= k for r in z) / len(z), 3)})
        if rowsk:
            res["threes_check"][str(k)] = rowsk
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


def grade_games(data, dates):
    """Score and winner predictions against final scores, next to the market."""
    rows = []
    for d in dates:
        final = {r["game_id"]: r for r in read_csv(data / "teamstats" / f"{d}.csv") if str(r["home"]).lower() == "true"}
        for r in read_csv(data / "gamepreds" / f"{d}.csv"):
            t = final.get(r["game_id"])
            if t:
                rows.append((r, fnum(t["PTS"]), fnum(t["OPP_PTS"])))
    if not rows:
        return None
    n = len(rows)
    out = {"games": n,
           "winner_hit": round(sum((fnum(r["margin"]) > 0) == (hp > ap) for r, hp, ap in rows) / n, 3),
           "margin_mae": round(statistics.mean(abs(fnum(r["margin"]) - (hp - ap)) for r, hp, ap in rows), 1),
           "total_mae": round(statistics.mean(abs(fnum(r["total"]) - (hp + ap)) for r, hp, ap in rows), 1),
           "team_score_mae": round(statistics.mean((abs(fnum(r["home_pts"]) - hp) + abs(fnum(r["away_pts"]) - ap)) / 2 for r, hp, ap in rows), 1)}
    m = [(r, hp, ap) for r, hp, ap in rows if fnum(r["spread"]) is not None]
    out["market_games"] = len(m)
    if m:
        sp = [x for x in m if fnum(x[0]["spread"]) != 0]
        out["market_winner_hit"] = round(sum((fnum(r["spread"]) < 0) == (hp > ap) for r, hp, ap in sp) / len(sp), 3) if sp else None
        out["market_margin_mae"] = round(statistics.mean(abs(-fnum(r["spread"]) - (hp - ap)) for r, hp, ap in m), 1)
        out["model_margin_mae_same_games"] = round(statistics.mean(abs(fnum(r["margin"]) - (hp - ap)) for r, hp, ap in m), 1)
        mt = [x for x in m if fnum(x[0]["market_total"]) is not None]
        out["market_total_mae"] = round(statistics.mean(abs(fnum(r["market_total"]) - (hp + ap)) for r, hp, ap in mt), 1) if mt else None
    # do the win chances mean what they say?
    cal = []
    for label, lo, hi in (("50 to 60%", .5, .6), ("60 to 70%", .6, .7), ("70 to 80%", .7, .8), ("80% and up", .8, 1.01)):
        z = [(max(fnum(r["home_win"]), 1 - fnum(r["home_win"])), (fnum(r["home_win"]) >= .5) == (hp > ap)) for r, hp, ap in rows]
        z = [w for p_, w in z if lo <= p_ < hi]
        if z:
            cal.append({"bucket": label, "n": len(z), "won": round(sum(z) / len(z), 3)})
    out["win_check"] = cal
    return out


# ------------------------------------------------------------------- report

CLOSE = {"PTS": 3, "REB": 2, "AST": 2, "3PM": 1}     # "close" in the stat's own units


def report_group(z):
    """How a set of graded player-stat rows did against their expected number, floor and ceiling."""
    f = lambda r, k: fnum(r.get(k))
    z = [r for r in z if f(r, "expected") is not None and f(r, "actual") is not None]
    if not z:
        return None
    stat = z[0]["stat"]
    n = len(z)
    pos = [r for r in z if f(r, "expected") > 0]
    ratios = sorted(f(r, "actual") / f(r, "expected") for r in pos)
    share = lambda test, rows=z: round(sum(1 for r in rows if test(r)) / len(rows), 3) if rows else None
    out = {"n": n,
           "avg_expected": round(statistics.mean(f(r, "expected") for r in z), 2),
           "avg_actual": round(statistics.mean(f(r, "actual") for r in z), 2),
           "bias": round(statistics.mean(f(r, "actual") - f(r, "expected") for r in z), 2),
           "mae": round(statistics.mean(abs(f(r, "actual") - f(r, "expected")) for r in z), 2),
           "reached": share(lambda r: f(r, "actual") >= f(r, "expected")),
           "within10": share(lambda r: f(r, "actual") >= 0.9 * f(r, "expected")),
           "within20": share(lambda r: f(r, "actual") >= 0.8 * f(r, "expected")),
           "close_abs": share(lambda r: f(r, "actual") >= f(r, "expected") - CLOSE[stat]),
           "way_short": share(lambda r: f(r, "actual") < 0.6 * f(r, "expected")),
           "ladder": {str(k): share(lambda r, k=k: f(r, "actual") >= k / 100 * f(r, "expected")) for k in (100, 90, 80, 70, 60, 50)},
           # the share of his expected number a player reached 4 times out of 5, and 2 times out of 3
           "reach80": round(ratios[int(0.20 * (len(ratios) - 1))], 2) if ratios else None,
           "reach67": round(ratios[int(0.33 * (len(ratios) - 1))], 2) if ratios else None}
    nv = [r for r in z if f(r, "season_avg") is not None]
    if nv:
        out["naive_mae"] = round(statistics.mean(abs(f(r, "actual") - f(r, "season_avg")) for r in nv), 2)
        out["mae_same"] = round(statistics.mean(abs(f(r, "actual") - f(r, "expected")) for r in nv), 2)
    for key, name in (("floor", "floor_hit"), ("ceiling", "ceiling_hit")):
        q = [r for r in z if f(r, key) is not None]
        out[name] = share(lambda r: f(r, "actual") >= f(r, key), q)
        out[name + "_n"] = len(q)
    lost = [r for r in z if f(r, "team_margin") is not None and f(r, "team_margin") <= -BLOWOUT]
    for key, name in (("floor", "lost_floor"), ("loss_floor", "lost_blowout_floor")):
        q = [r for r in lost if f(r, key) is not None]
        out[name] = share(lambda r: f(r, "actual") >= f(r, key), q)
        out[name + "_n"] = len(q)
    return out


def report_lines(z):
    """How projections and over chances did against the posted prop lines."""
    f = lambda r, k: fnum(r.get(k))
    z = [r for r in z if f(r, "line") is not None and f(r, "p_over") is not None and f(r, "actual") is not None]
    if not z:
        return None
    share = lambda test, rows: round(sum(1 for r in rows if test(r)) / len(rows), 3) if rows else None
    over = lambda r: f(r, "actual") > f(r, "line")
    out = {"n": len(z), "went_over": share(over, z),
           "avg_chance": round(statistics.mean(f(r, "p_over") for r in z), 3),
           "model_mae": round(statistics.mean(abs(f(r, "actual") - f(r, "expected")) for r in z), 2),
           "line_mae": round(statistics.mean(abs(f(r, "actual") - f(r, "line")) for r in z), 2),
           "model_closer": share(lambda r: abs(f(r, "actual") - f(r, "expected")) < abs(f(r, "actual") - f(r, "line")), z),
           "buckets": []}
    for label, lo, hi in (("under 30%", 0, .3), ("30 to 40%", .3, .4), ("40 to 50%", .4, .5), ("50 to 60%", .5, .6),
                          ("60 to 70%", .6, .7), ("70% and up", .7, 1.01)):
        q = [r for r in z if lo <= f(r, "p_over") < hi]
        if q:
            out["buckets"].append({"bucket": label, "n": len(q), "went_over": share(over, q),
                                   "avg_chance": round(statistics.mean(f(r, "p_over") for r in q), 3)})
    hi_, lo_ = [r for r in z if f(r, "p_over") >= 0.6], [r for r in z if f(r, "p_over") <= 0.4]
    out["lean_over"] = {"n": len(hi_), "right": share(over, hi_)}
    out["lean_under"] = {"n": len(lo_), "right": share(lambda r: f(r, "actual") < f(r, "line"), lo_)}
    fl = [r for r in z if f(r, "floor") is not None and f(r, "floor") > f(r, "line")]
    out["floor_above_line"] = {"n": len(fl), "went_over": share(over, fl)}
    return out


def build_report(every, docs):
    """Everything the Report page shows. Rebuilt from the graded files each morning."""
    played = [r for r in every if str(r["played"]) == "True"]
    groups = (("everyone", lambda r: True), ("stars", lambda r: str(r["star"]) == "True"),
              ("starters", lambda r: r["role"] == "starter" and str(r["star"]) != "True"),
              ("bench", lambda r: r["role"] == "bench"))
    sizes = {"PTS": ((25, 99, "25 or more"), (18, 25, "18 to 25"), (12, 18, "12 to 18"), (0, 12, "under 12")),
             "REB": ((8, 99, "8 or more"), (5, 8, "5 to 8"), (0, 5, "under 5")),
             "AST": ((6, 99, "6 or more"), (3, 6, "3 to 6"), (0, 3, "under 3")),
             "3PM": ((2.5, 99, "2.5 or more"), (1.5, 2.5, "1.5 to 2.5"), (0, 1.5, "under 1.5"))}

    def scope(rows):
        if not rows:
            return None
        out = {"nights": len({r["date"] for r in rows}), "player_games": len({(r["date"], r["player_id"]) for r in rows}),
               "from": min(r["date"] for r in rows), "to": max(r["date"] for r in rows), "stats": {}, "lines": {}}
        for s in STATS:
            z = [r for r in rows if r["stat"] == s]
            out["stats"][s] = {"groups": {name: report_group([r for r in z if test(r)]) for name, test in groups},
                               "by_size": [dict(report_group([r for r in z if lo <= fnum(r["expected"], 0) < hi]) or {}, label=label)
                                           for lo, hi, label in sizes[s]]}
            out["lines"][s] = report_lines(z)
        out["lines"]["all"] = report_lines(rows)
        return out

    nights = []
    for d in sorted({r["date"] for r in played}):
        z = [r for r in played if r["date"] == d]
        pts = report_group([r for r in z if r["stat"] == "PTS"])
        row = {"date": d, "live": dt.date.fromisoformat(d) >= LIVE_FROM, "players": len({r["player_id"] for r in z}),
               "games": len({r["game_id"] for r in z})}
        for s in STATS:
            g = report_group([r for r in z if r["stat"] == s])
            row[s] = {k: g.get(k) for k in ("reached", "within20", "floor_hit", "mae", "naive_mae", "bias")} if g else None
        ln = report_lines(z)
        row["lines"] = {"n": ln["n"], "went_over": ln["went_over"], "model_closer": ln["model_closer"]} if ln else None
        nights.append(row)

    last_date = max(r["date"] for r in played) if played else None
    last = [r for r in played if r["date"] == last_date]
    def card(r):
        return {"player": r["player"], "team": r["team"], "stat": r["stat"], "expected": fnum(r["expected"]),
                "actual": fnum(r["actual"]), "floor": fnum(r["floor"]), "line": fnum(r.get("line")),
                "minutes": fnum(r["actual_minutes"]), "proj_minutes": fnum(r["minutes"])}
    beats, misses = {}, {}
    for s in STATS:         # biggest beats and misses of the last slate, for each stat
        by_gap = sorted([r for r in last if r["stat"] == s], key=lambda r: fnum(r["actual"]) - fnum(r["expected"]))
        misses[s] = [card(r) for r in by_gap[:8]]
        beats[s] = [card(r) for r in by_gap[::-1][:8]]
    report = {
        "generated_et": dt.datetime.now(ET).strftime("%Y-%m-%d %I:%M %p ET"), "live_from": str(LIVE_FROM), "model": MODEL_VERSION,
        "close": CLOSE,
        "live": scope([r for r in played if dt.date.fromisoformat(r["date"]) >= LIVE_FROM]),
        "all": scope(played),
        "last": {"date": last_date, "scope": scope(last), "misses": misses, "beats": beats},
        "nights": nights,
    }
    (docs / "data").mkdir(parents=True, exist_ok=True)
    (docs / "data" / "report.json").write_text(json.dumps(report, separators=(",", ":")))
    return report


def run_grade(date, data, docs):
    rows = grade_one(date, data)
    if rows is None:
        print(f"nothing to grade for {date} (need projections, box scores and team stats)")
        return
    last, games = summarize_grades(rows)
    last["date"] = str(date)
    last["left_early"] = sorted({f"{r['player']} ({fnum(r['actual_minutes']):.0f} min)" for r in rows if left_early(r)})
    last["did_not_play"] = sorted({r["player"] for r in rows if str(r["played"]) != "True"})
    last["blowout_calls"] = [{"game": f"{g[3]} / {g[2]}", "p_blowout": g[0], "margin": g[1]}
                             for g in sorted(games.values(), key=lambda g: -g[0])]
    every = []
    for p in sorted((data / "graded").glob("*.csv")):
        every.extend(read_csv(p))
    allnights, _ = summarize_grades(every)
    allnights["nights"] = len({r["date"] for r in every})
    last["game_preds"] = grade_games(data, [str(date)])
    allnights["game_preds"] = grade_games(data, sorted(p.stem for p in (data / "gamepreds").glob("*.csv")))
    (docs / "data").mkdir(parents=True, exist_ok=True)
    # the live record: only slates projected before tip by the scheduled runs
    live_rows = [r for r in every if dt.date.fromisoformat(r["date"]) >= LIVE_FROM]
    live = None
    if live_rows:
        live, _ = summarize_grades(live_rows)
        live["nights"] = len({r["date"] for r in live_rows})
        live["game_preds"] = grade_games(data, sorted(p.stem for p in (data / "gamepreds").glob("*.csv")
                                                      if dt.date.fromisoformat(p.stem) >= LIVE_FROM))
    (docs / "data" / "grade.json").write_text(json.dumps(
        {"last": last, "all": allnights, "live": live, "live_from": str(LIVE_FROM), "model": MODEL_VERSION},
        separators=(",", ":")))
    build_report(every, docs)
    s = last["stats"].get("PTS", {})
    print(f"graded {date}: {last['player_games']} player-games, PTS bias {s.get('bias')} MAE {s.get('mae')}, "
          f"floor hit {s.get('floor_hit')}; all nights: {allnights['nights']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["project", "grade"])
    ap.add_argument("--date", help="YYYY-MM-DD; default is today (US Eastern) for project, yesterday for grade")
    ap.add_argument("--data", default="data")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--now", help="testing: pretend the run happens at this UTC time (ISO format)")
    a = ap.parse_args()
    today = dt.datetime.now(ET).date()
    if a.date:
        date = dt.date.fromisoformat(a.date)
    else:
        date = today if a.cmd == "project" else today - dt.timedelta(days=1)
    data, docs = pathlib.Path(a.data), pathlib.Path(a.docs)
    if a.cmd == "grade":
        if a.date:
            return run_grade(date, data, docs)
        # no date given: catch up on the last few days, oldest first, so a missed morning heals itself
        for back in (4, 3, 2, 1):
            run_grade(today - dt.timedelta(days=back), data, docs)
        return
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=dt.timezone.utc) if a.now else None
    # a past date is a replay: every game is projected fresh, nothing is locked
    run_project(date, data, docs, now=now, lock=(date >= today))


if __name__ == "__main__":
    main()
