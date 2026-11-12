// Renders docs/data/latest.json (tonight) and docs/data/grade.json (record).
// Both files are written by scripts/nightly.py. This page does no math of its own.
(function () {
  var STATS = ['PTS', 'REB', 'AST', '3PM'], CEIL = ['PTS', 'REB', 'AST', '3PM', 'STL', 'BLK'];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function dash(v) { return v == null || v === '' ? '-' : v; }
  function pc(v) { return v == null ? '-' : Math.round(v * 100) + '%'; }
  function rel(v) { var d = Math.round((v - 1) * 100); return (d > 0 ? '+' : '') + d + '%'; }
  function tagEl(t) { return '<span class="tag ' + (t || 'none') + '">' + (t || 'no line') + '</span>'; }
  function spreadTxt(g) { return g.favorite ? esc(g.favorite) : (g.pred ? 'model ' + esc(g.pred.margin >= 0 ? g.home : g.away) + ' -' + Math.abs(g.pred.margin).toFixed(1) : 'no spread'); }
  function heat(v) {
    if (v == null) return '';
    var d = v - 1, a = Math.min(0.5, Math.abs(d) * 4);
    return 'background:rgba(var(--' + (d >= 0 ? 'good' : 'bad') + '-rgb),' + a.toFixed(2) + ')';
  }
  function ml(v) { return v == null ? '-' : (v > 0 ? '+' : '') + v; }
  function gp(x) {
    var p = x.game_preds; if (!p) return '';
    var t = '<p><b>Game predictions.</b> Winner right in ' + pc(p.winner_hit) + ' of ' + p.games + ' games. Avg miss: margin ' + p.margin_mae + ', total ' + p.total_mae + ', team score ' + p.team_score_mae + '.';
    if (p.market_games) t += ' The betting line on the same nights: favorite won ' + pc(p.market_winner_hit) + ', margin miss ' + p.market_margin_mae + ', total miss ' + dash(p.market_total_mae) + '.';
    if (p.win_check && p.win_check.length && p.games >= 30) t += ' Win chance check: ' + p.win_check.map(function (b) { return b.bucket + ' picks won ' + pc(b.won) + ' (' + b.n + ')'; }).join(' · ') + '.';
    return t + '</p>';
  }
  function adjNote(g) {
    var p = g.pred; if (!p) return '';
    return [[g.away, p.away_adj], [g.home, p.home_adj]].map(function (x) {
      var a = x[1]; if (!a || !a.minus) return '';
      var why = a.missing.slice(0, 2).map(esc); if (a.missing.length > 2) why.push('+' + (a.missing.length - 2) + ' more'); if (a.b2b) why.push('back-to-back');
      return esc(x[0]) + ' -' + a.minus + ' pts: ' + why.join(', ');
    }).filter(Boolean).join(' · ');
  }
  function tipTxt(g) { return new Date(g.tip).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET'; }
  function gamesGrid(D) {
    return '<section id="games"><div class="eyebrow">Tonight\'s games</div><div class="gcards">' + D.games.map(function (g) {
      var p = g.pred, rows = '';
      if (p) {
        var hw = p.home_win, pickHome = hw >= 0.5;
        rows = [[g.away, p.away_pts, 1 - hw, p.away_ml, !pickHome], [g.home, p.home_pts, hw, p.home_ml, pickHome]].map(function (r) {
          return '<div class="gteam' + (r[4] ? ' pick' : '') + '"><span class="ab">' + esc(r[0]) + '</span><span class="sc">' + r[1].toFixed(1) + '</span><span class="wp">' + pc(r[2]) + '</span><span class="mlv">' + ml(r[3]) + '</span></div>';
        }).join('') + '<div class="winbar" title="win chance"><i style="width:' + Math.round((1 - hw) * 100) + '%"></i></div>';
      }
      var line = g.favorite ? 'Line ' + esc(g.favorite) + (g.total != null ? ' · O/U ' + g.total : '') : 'No line posted';
      var cmp = '';
      if (p && p.market_home_pts != null) {
        var d = p.margin + g.spread;   // model margin minus line margin, home side
        cmp = Math.abs(d) < 3 ? 'Model agrees with the line' : 'Model leans ' + esc(d > 0 ? g.home : g.away) + ' by ' + Math.abs(d).toFixed(1) + ' more than the line';
      }
      var adj = adjNote(g);
      return '<a class="gc" href="#g-' + g.game_id + '"><div class="gtop"><span class="gtime">' + tipTxt(g) + (g.locked ? ' · locked' : '') + '</span>' + tagEl(g.tag) + '</div>' +
        (p ? '<div class="ghdr"><span></span><span>score</span><span>win</span><span>fair ML</span></div>' : '') + rows +
        '<div class="gmeta">' + line + '</div><div class="gmeta">Blowout risk ' + pc(g.p_blowout) + (cmp ? ' · ' + cmp : '') + '</div>' +
        (adj ? '<div class="gmeta adj">' + adj + '</div>' : '') + '</a>';
    }).join('') + '</div><p class="lead" style="margin-top:12px">Projected score and win chance come from team scoring and defense per possession, pace, home court, missing players and back-to-backs. Fair ML is the win chance written as odds with no sportsbook fee. Blowout risk is the chance of a 20 point margin, and stars lose minutes in those games. Tap a game to jump to its players.</p></section>';
  }
  // Position matchups. SOFT/TOUGH are raw gaps in what a defense has allowed to a position.
  // Checked on 1,419 player-games (Oct 30 to Nov 11, 2026): about a fifth of the raw gap
  // carried over. Points rose against soft spots but did not fall against tough ones, and
  // threes showed no pattern by position, so those are not flagged.
  var SOFT = 1.12, TOUGH = 0.88, MSTATS = ['PTS', 'REB', 'AST'], PNAME = { G: 'Guards', F: 'Forwards', C: 'Centers' }, MINV = { PTS: 8, REB: 4, AST: 3 };
  function spot(t, pos, s) {
    var v = t.dvp && t.dvp[pos] ? t.dvp[pos][s] : null;
    if (v == null || MSTATS.indexOf(s) < 0) return 0;
    if (v >= SOFT) return 1;
    if (v <= TOUGH && s !== 'PTS') return -1;
    return 0;
  }
  function mark(k) { return k > 0 ? '<span class="mk up" title="Soft position matchup">▲</span>' : (k < 0 ? '<span class="mk down" title="Tough position matchup">▼</span>' : ''); }
  function matchups(D) {
    var blocks = []; D.games.forEach(function (g) { g.teams.forEach(function (t) { if (t.dvp) blocks.push({ g: g, t: t }); }); });
    if (!blocks.length) return '';
    var soft = [], tough = [];
    blocks.forEach(function (b) {
      ['G', 'F', 'C'].forEach(function (pos) {
        MSTATS.forEach(function (s) {
          var k = spot(b.t, pos, s); if (!k) return;
          var pl = b.t.players.filter(function (p) { return p.pos === pos && p.stats[s].expected >= MINV[s]; }).sort(function (x, y) { return y.stats[s].expected - x.stats[s].expected; }).slice(0, 3);
          if (!pl.length) return;
          (k > 0 ? soft : tough).push({ v: b.t.dvp[pos][s], pos: pos, s: s, def: b.t.opp, team: b.t.team, gid: b.g.game_id, pl: pl });
        });
      });
    });
    soft.sort(function (a, b) { return b.v - a.v; }); tough.sort(function (a, b) { return a.v - b.v; });
    function item(x) {
      return '<a class="tg mlink" href="#g-' + x.gid + '"><div class="g">' + esc(x.team) + ' ' + PNAME[x.pos].toLowerCase() + ' · ' + x.s + ' <span class="' + (x.v > 1 ? 'up' : 'down') + '">' + rel(x.v) + '</span></div><div class="m">' + esc(x.def) + ' defense vs ' + PNAME[x.pos].toLowerCase() + ', so far</div>' +
        '<div class="p">' + x.pl.map(function (p) { return esc(p.name) + ' ' + p.stats[x.s].expected; }).join(' · ') + '</div></a>';
    }
    function card(title, list, empty) {
      return '<div class="card"><h3>' + title + '</h3><div class="body">' + (list.length ? list.slice(0, 8).map(item).join('') : '<div class="tg"><div class="p">' + empty + '</div></div>') + '</div></div>';
    }
    var tbl = '<div class="ceilwrap" style="margin-top:12px"><table class="ceil"><thead><tr><th class="lft" rowspan="2">Defense</th>' + MSTATS.map(function (s) { return '<th class="grp" colspan="3">' + s + ' allowed</th>'; }).join('') + '</tr><tr>' +
      MSTATS.map(function () { return '<th class="grp">G</th><th>F</th><th>C</th>'; }).join('') + '</tr></thead><tbody>' +
      blocks.map(function (b) {
        return '<tr><td class="g lft">' + esc(b.t.opp) + ' <span class="date">vs ' + esc(b.t.team) + '</span></td>' + MSTATS.map(function (s) {
          return ['G', 'F', 'C'].map(function (pos, i) { var v = b.t.dvp[pos][s], k = spot(b.t, pos, s); return '<td' + (i ? '' : ' class="gl"') + '><span class="cv" style="' + (Math.abs(v - 1) >= 0.12 ? heat(v) : '') + '">' + rel(v) + '</span>' + mark(k) + '</td>'; }).join('');
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
    return '<section id="matchups"><div class="eyebrow">Position matchups</div><div class="grid2">' +
      card('▲ Soft spots tonight', soft, 'No defense tonight has been 12% or more above average against a position.') +
      card('▼ Tough spots tonight', tough, 'No defense tonight has been 12% or more below average against a position in rebounds or assists.') + '</div>' + tbl +
      '<p class="lead" style="margin-top:10px">Percentages are what each defense has allowed to that position so far, against the league average. They are small samples, so read them as a lean. On 1,419 player-games this season about a fifth of the gap carried over to the next game: a defense that had allowed 25% more to a position meant about 5% more for the next player there. Points rose against soft spots but did not fall against tough ones, and threes showed no pattern by position, so those are not flagged. The projections already include this at that strength.</p></section>';
  }
  function load(u) { return fetch(u, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }

  function gradeBlock(G) {
    if (!G) return '<section id="record"><div class="eyebrow">Last slate grade and record</div><p class="lead">No graded nights yet. This fills in the morning after the first projected slate.</p></section>';
    function rows(x) {
      return STATS.map(function (s) {
        var a = x.stats[s]; if (!a) return '';
        return '<tr><td class="pl">' + s + '</td><td>' + a.n + '</td><td>' + (a.bias > 0 ? '+' : '') + a.bias + '</td><td>' + a.mae + '</td><td>' + pc(a.floor_hit) +
          '</td><td>' + pc(a.floor_hit_full) + '</td><td>' + pc(a.blowout_floor_hit) + ' <span class="dim">(' + a.blowout_floor_n + ')</span></td><td>' + pc(a.rule_floor_hit_log) + '</td><td>' + pc(a.rule_floor_hit_flat) + '</td></tr>';
      }).join('');
    }
    function tbl(x) {
      return '<div class="tscroll"><table><thead><tr><th class="lft">Stat</th><th>Players</th><th>Avg miss</th><th>Avg abs miss</th><th>Floor hit</th><th title="Leaving out players who left early">Full games</th><th>Blowout floor hit</th><th>Log rule</th><th>Flat rule</th></tr></thead><tbody>' + rows(x) + '</tbody></table></div>';
    }
    function mins(x) {
      var c = x.star_minutes_close, b = x.star_minutes_blowout, o = [];
      if (c) o.push('Games within 20: projected ' + c.projected + ', actual ' + c.actual + ' (' + c.n + ' stars).');
      if (b) o.push('Games decided by 20 or more: projected ' + b.projected + ', actual ' + b.actual + ' (' + b.n + ' stars).');
      return o.join(' ');
    }
    function tags(x) {
      return ['Low', 'Medium', 'High'].map(function (t) { var z = x.blowout_by_tag[t]; return t + ': ' + z.ended_by_20 + ' of ' + z.games; }).join(' · ');
    }
    function over(x) {
      if (!x.over_check || !x.over_check.length) return 'No prop lines graded yet.';
      return x.over_check.map(function (b) { return b.bucket + ': went over ' + pc(b.went_over) + ' (' + b.n + ')'; }).join(' · ') +
        (x.line_check ? '. Avg abs miss: model ' + x.line_check.model_mae + ', line ' + x.line_check.line_mae + '.' : '');
    }
    var L = G.last, A = G.all;
    var calls = L.blowout_calls.map(function (c) { return esc(c.game) + ' ' + pc(c.p_blowout) + ' → final margin ' + c.margin; }).join(' · ');
    return '<section id="record"><div class="eyebrow">Last slate grade and all-nights record</div><div class="grid2">' +
      '<div class="card"><h3>Last slate · ' + esc(L.date) + ' · ' + L.player_games + ' player-games</h3>' + tbl(L) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(L.star_floor_hit) + ' of ' + L.star_floors + ' held' + (L.left_early_n ? ', or ' + pc(L.star_floor_hit_full) + ' of ' + L.star_floors_full + ' leaving out players who left early' : '') + '.</p>' +
      (L.left_early && L.left_early.length ? '<p><b>Left early (' + L.left_early.length + '):</b> ' + L.left_early.map(esc).join(', ') + '. Starters who played under half their projected minutes in a game that was not a blowout, usually an injury.</p>' : '') +
      '<p><b>Star minutes.</b> ' + mins(L) + '</p><p><b>Blowout calls.</b> ' + calls + '</p>' +
      gp(L) + '<p><b>Projected but did not play (' + L.did_not_play.length + '):</b> ' + (L.did_not_play.map(esc).join(', ') || 'none') + '</p></div></div>' +
      '<div class="card"><h3>All nights · ' + A.nights + ' nights · ' + A.player_games + ' player-games</h3>' + tbl(A) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(A.star_floor_hit) + ' of ' + A.star_floors + ' held' + (A.left_early_n ? ', or ' + pc(A.star_floor_hit_full) + ' of ' + A.star_floors_full + ' leaving out the ' + A.left_early_n + ' players who left early' : '') + '. The target is about 80%.</p>' +
      '<p><b>Star minutes.</b> ' + mins(A) + '</p><p><b>Games decided by 20 or more, by tag.</b> ' + tags(A) + '</p>' +
      '<p><b>Over-chance check.</b> ' + over(A) + '</p>' + gp(A) + '</div></div></div></section>';
  }

  function targets(D) {
    return '<section id="targets"><div class="eyebrow">Target games by stat</div><div class="grid2">' + CEIL.map(function (s) {
      var t = D.targets[s] || [];
      var body = t.length ? t.map(function (g) {
        return '<div class="tg"><div class="g">' + esc(g.away) + ' at ' + esc(g.home) + ' ' + tagEl(g.tag) + '</div><div class="m">index ' + g.index.toFixed(2) + ' · total ' + dash(g.total) +
          (g.tag === 'High' ? ' · stars may sit late' : '') + '</div>' +
          (g.players.length ? '<div class="p">' + g.players.map(function (p) { return esc(p.name) + ' ' + p.expected; }).join(' · ') + '</div>' : '') + '</div>';
      }).join('') : '<div class="tg"><div class="p">No standout game tonight.</div></div>';
      return '<div class="card"><h3>' + s + '</h3><div class="body">' + body + '</div></div>';
    }).join('') + '</div><p class="lead" style="margin-top:10px">Index 1.00 is an average NBA game for that stat. It is what both defenses allow, compared with the league.</p></section>';
  }

  function safest(D) {
    if (!D.safest.length) return '';
    var anyLine = D.safest.some(function (r) { return r.line != null; });
    return '<section id="floors"><div class="eyebrow">' + (anyLine ? 'Safest lines' : 'Steadiest floors') + '</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Player</th><th>Stat</th><th>Expected</th><th>Line</th><th>Over chance</th><th>Floor</th><th>Blowout floor</th></tr></thead><tbody>' +
      D.safest.map(function (r) {
        return '<tr><td class="g lft">' + esc(r.name) + ' <span class="date">' + esc(r.team) + '</span></td><td>' + r.stat + '</td><td>' + r.expected + '</td><td>' + dash(r.line) + '</td><td>' + pc(r.p_over) + '</td><td>' + r.floor + '</td><td>' + dash(r.blowout_floor) + '</td></tr>';
      }).join('') + '</tbody></table></div>' + (anyLine ? '' : '<p class="lead" style="margin-top:10px">No prop lines were loaded tonight, so these are the stars whose floor sits closest to their expected value.</p>') + '</section>';
  }

  function gameTable(g, anyLine, mode) {
    var all = mode === 'ALL', head, cols, body = '';
    if (all) {
      var per = anyLine ? 4 : 2;
      head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th>' + STATS.map(function (s) { return '<th class="grp" colspan="' + per + '">' + s + '</th>'; }).join('') + '</tr>' +
        '<tr><th></th><th></th><th></th>' + STATS.map(function () { return '<th class="grp">Exp</th><th>Floor</th>' + (anyLine ? '<th>Line</th><th>Over</th>' : ''); }).join('') + '</tr>';
      cols = 3 + per * 4;
    } else {
      head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th><th>Season</th><th>Expected</th><th>Floor</th><th>Blowout floor</th><th>Normal game</th><th>Blowout game</th><th>Matchup</th>' + (anyLine ? '<th>Line</th><th>Over chance</th>' : '') + '</tr>';
      cols = 10 + (anyLine ? 2 : 0);
    }
    g.teams.forEach(function (t) {
      var a = t.area;
      body += '<tr class="teamsplit"><td colspan="' + cols + '">' + esc(t.team) + ' <span class="vs">vs ' + esc(t.opp) + ' defense: threes ' + rel(a.f3) + ', paint ' + rel(a.fpaint) + ', free throws ' + rel(a.fft) +
        (t.b2b ? ' · back-to-back' : '') + (t.out_scorers.length ? ' · out: ' + t.out_scorers.map(esc).join(', ') : '') + '</span></td></tr>';
      var bench = false;
      t.players.forEach(function (p) {
        if (p.role === 'bench' && !bench) { bench = true; body += '<tr class="benchrow"><td colspan="' + cols + '">Bench</td></tr>'; }
        var nm = '<td class="pos">' + p.pos + '</td><td class="pl">' + esc(p.name) + (p.star ? '<span class="starmk" title="18 or more points a game">★</span>' : '') + (p.gtd ? '<span class="gtd">GTD</span>' : '') + '</td><td class="dim">' + p.min + '</td>';
        var key = ' data-n="' + esc(p.name.toLowerCase()) + '"';
        if (all) {
          body += '<tr class="prow' + (p.star ? ' hasub' : '') + '"' + key + '>' + nm + STATS.map(function (s) {
            var x = p.stats[s];
            return '<td class="ex gl">' + mark(spot(t, p.pos, s)) + x.expected + (x.check ? '<span class="chk">check</span>' : '') + '</td><td class="fl">' + x.floor + '</td>' + (anyLine ? '<td class="dim">' + dash(x.line) + '</td><td>' + pc(x.p_over) + '</td>' : '');
          }).join('') + '</tr>';
          if (p.star) body += '<tr class="prow"' + key + '><td class="sub"></td><td class="sub" colspan="2">normal / blowout / blowout floor</td>' +
            STATS.map(function (s) { var x = p.stats[s]; return '<td class="sub gl" colspan="' + per + '" style="text-align:right">' + x.normal + ' / ' + x.blowout + ' / ' + dash(x.blowout_floor) + '</td>'; }).join('') + '</tr>';
        } else {
          var x = p.stats[mode], m = x.matchup == null ? null : x.matchup * (x.bump || 1);
          body += '<tr class="prow"' + key + '>' + nm + '<td class="dim">' + p.season[mode] + '</td><td class="ex">' + mark(spot(t, p.pos, mode)) + x.expected + (x.check ? '<span class="chk">check</span>' : '') + '</td><td class="fl">' + x.floor + '</td><td class="fl">' + dash(x.blowout_floor) +
            '</td><td class="dim">' + x.normal + '</td><td class="dim">' + x.blowout + '</td><td class="' + (m == null || Math.abs(m - 1) < 0.03 ? 'dim' : (m > 1 ? 'up' : 'down')) + '">' + (m == null ? '-' : rel(m)) + '</td>' +
            (anyLine ? '<td class="dim">' + dash(x.line) + '</td><td>' + pc(x.p_over) + '</td>' : '') + '</tr>';
        }
      });
    });
    var pick = g.pred ? ' · model ' + esc(g.pred.margin >= 0 ? g.home : g.away) + ' by ' + Math.abs(g.pred.margin).toFixed(1) : '';
    return '<details class="game" id="g-' + g.game_id + '" open><summary class="ghead"><span class="ttl">' + esc(g.away) + ' at ' + esc(g.home) + '</span><div class="meta"><span class="pill">' + tipTxt(g) + '</span><span class="pill">' + spreadTxt(g) +
      '</span><span class="pill ou">O/U ' + dash(g.total) + '</span>' + tagEl(g.tag) + (g.locked ? '<span class="pill">locked at tip</span>' : '') + '</div></summary><div class="tscroll"><table class="' + (all ? 'tall' : 'tone') + '"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div></details>';
  }

  function ceiling(D) {
    return '<section id="ceiling"><div class="eyebrow">Ceiling index</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Game</th>' + CEIL.map(function (s) { return '<th>' + s + '</th>'; }).join('') + '<th>Pace</th></tr></thead><tbody>' +
      D.games.map(function (g) {
        return '<tr><td class="g lft">' + esc(g.away) + ' at ' + esc(g.home) + '</td>' + CEIL.map(function (s) {
          var v = g.ceiling[s], flag = v != null && (v >= 1.08 || v <= 0.92);
          return '<td><span class="cv" style="' + (flag ? heat(v) : '') + '">' + (v == null ? '-' : v.toFixed(2)) + '</span></td>';
        }).join('') + '<td>' + g.pace.toFixed(2) + '</td></tr>';
      }).join('') + '</tbody></table></div><p class="lead" style="margin-top:10px">Shaded cells are 8% or more above or below an average game.</p></section>';
  }

  function method(D) {
    var m = D.method;
    return '<section id="method"><details class="fold"><summary class="eyebrow">Method and limits</summary><div class="method">' +
      '<p><b>Source.</b> Everything comes from ESPN box scores, odds and injury reports saved in this repo. Player rates, recent form, starters, defense by position (guard, forward, center), area defense (threes, paint, free throws) and pace are all built from those box scores.</p>' +
      '<p><b>History.</b> ' + m.history_days + ' game days, ' + esc(m.history_from) + ' to ' + esc(m.history_to) + '. ' + m.players + ' players projected. ' + m.log_floors + ' floors use the player\'s own game log and ' + m.flat_floors + ' use the flat rule.</p>' +
      '<p><b>Blowout minutes.</b> In a blowout, players at 30 or more minutes are projected to keep 87% of their minutes, which is what the record measured. Floors use a more cautious 80%. With 87% in the floors, star blowout floors held 71% of the time on the replay, against 80% with the cautious number.</p>' +
      '<p><b>Blowouts.</b> Final margins are assumed to land around the spread with a typical miss of ' + (m.sd || 13) + ' points. That was 13 until Nov 11, 2026, when 159 games this season showed blowouts happening more often than 13 allows. Tags: Low under 21%, Medium 21 to 27%, High over 27%.</p>' +
      '<p><b>Game predictions.</b> A missing rotation player costs his team half of what he scores beyond an average teammate in the same minutes, scaled down if the team has already played games without him. A back-to-back costs 1.5 points. On 108 replayed games these two adjustments did not measurably change accuracy, so treat them as reasonable assumptions that the nightly record will confirm or not.</p>' +
      '<p><b>Minutes swing.</b> Minutes are simulated with a night-to-night swing of 6 for bench players, 5 for starters under 18 points a game and 3 for stars. The first two match what the record shows. On the replay that moved bench points floors from 70% to 74% held and non-star starter floors from 76% to 79%.</p>' +
      '<p><b>Missing teammates.</b> When a 15-point scorer is out, each teammate\'s points rate is adjusted by how he has actually scored in games without that player, compared with his season rate, so a long absence is not counted twice. With few such games the number stays close to a small default lift. Assists use the default lift only. On 98 replayed cases this was about even with the old flat 5% rule, so it is not yet proven better.</p>' +
      '<p><b>Runs.</b> About 11:30am, 2:30pm, 5:37pm and 6:27pm ET. A game that has tipped keeps the numbers from the last run before tip' + (m.locked_games ? ' (' + m.locked_games + ' locked now)' : '') + '.</p>' +
      '<p><b>Lines.</b> ' + (m.lines_found ? m.lines_found + ' prop lines loaded. They never feed the projection.' : 'No prop lines loaded, so Line and Over chance are hidden.') + '</p>' +
      '<p><b>Limits.</b> Starters are taken from each team\'s last five games, not from tonight\'s posted lineup. Positions are ESPN\'s three groups. A late scratch after the run is not reflected.</p>' +
      '<p><b>Record.</b> Nights from Oct 30 to Nov 10, 2026 were replayed after the fact, each using only data from before that night. Later nights are graded live.</p>' +
      (m.notes.length ? '<p><b>Notes.</b> ' + m.notes.map(esc).join(' ') + '</p>' : '') + '</div></details></section>';
  }

  Promise.all([load('data/latest.json'), load('data/grade.json')]).then(function (r) {
    var D = r[0], G = r[1], app = document.getElementById('app');
    if (!D) { app.innerHTML = '<p class="empty">No projections yet. They appear after the first pregame run.</p>'; return; }
    document.getElementById('hdate').textContent = new Date(D.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) + ' · ' + D.games.length + ' games';
    document.getElementById('hrun').textContent = 'Updated ' + D.run_time_et.replace(/^\d{4}-\d{2}-\d{2} 0?/, '');
    document.getElementById('nav').hidden = false;
    var anyLine = D.method.lines_found > 0, mode = innerWidth < 760 ? 'PTS' : 'ALL';
    try { var saved = localStorage.getItem('nba-mode'); if (saved && (saved === 'ALL' || STATS.indexOf(saved) >= 0)) mode = saved; } catch (e) {}
    app.innerHTML = (D.early_run ? '<div class="warnbar">Early look. Injuries and spreads can still change. This page refreshes at about 2:31pm, 5:37pm and 6:27pm ET, and each game locks at its tip.</div>' : '') +
      gamesGrid(D) + matchups(D) + targets(D) + safest(D) +
      '<section id="players"><div class="eyebrow">Players, game by game</div><div class="controls"><input id="q" type="search" placeholder="Find a player" aria-label="Find a player">' +
      '<div class="seg" id="seg" role="group" aria-label="Stat shown">' + ['ALL'].concat(STATS).map(function (s) { return '<button type="button" data-m="' + s + '">' + (s === 'ALL' ? 'All stats' : s) + '</button>'; }).join('') + '</div>' +
      '<button type="button" class="tgl" id="fold">Collapse all</button></div>' +
      '<p class="lead" style="margin-bottom:14px">Expected already accounts for blowout risk. Floor is the number reached in 80% of 10,000 simulated games. Blowout floor is the same thing in games decided by 20 or more. ★ marks players at 18 or more points a game. ▲ and ▼ mark a soft or tough position matchup for that stat.</p>' +
      '<div id="tables"></div><p class="empty" id="nomatch" hidden>No player on tonight\'s slate matches that name.</p></section>' + ceiling(D) + gradeBlock(G) + method(D);

    var tables = document.getElementById('tables'), q = document.getElementById('q'), seg = document.getElementById('seg'), fold = document.getElementById('fold');
    function filter() {
      var v = q.value.trim().toLowerCase(), any = false;
      tables.querySelectorAll('details.game').forEach(function (d) {
        var hit = false;
        d.querySelectorAll('tr.prow').forEach(function (tr) { var ok = !v || tr.getAttribute('data-n').indexOf(v) >= 0; tr.hidden = !ok; if (ok) hit = true; });
        d.querySelectorAll('tr.teamsplit, tr.benchrow').forEach(function (tr) { tr.hidden = !!v; });
        d.hidden = !hit; if (v && hit) d.open = true; if (hit) any = true;
      });
      document.getElementById('nomatch').hidden = any;
    }
    function draw() {
      tables.innerHTML = D.games.map(function (g) { return gameTable(g, anyLine, mode); }).join('');
      seg.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-m') === mode ? 'true' : 'false'); });
      filter();
    }
    seg.addEventListener('click', function (e) {
      var m = e.target.getAttribute && e.target.getAttribute('data-m'); if (!m) return;
      mode = m; try { localStorage.setItem('nba-mode', m); } catch (err) {} draw();
    });
    q.addEventListener('input', filter);
    fold.addEventListener('click', function () {
      var open = fold.textContent === 'Expand all';
      tables.querySelectorAll('details.game').forEach(function (d) { d.open = open; });
      fold.textContent = open ? 'Collapse all' : 'Expand all';
    });
    draw();
    if (location.hash && document.getElementById(location.hash.slice(1))) document.getElementById(location.hash.slice(1)).scrollIntoView();
  });
})();
