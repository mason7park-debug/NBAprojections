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
  function gamePreds(D) {
    var gs = D.games.filter(function (g) { return g.pred; });
    if (!gs.length) return '';
    return '<section><div class="eyebrow">Game predictions</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Game</th><th>Projected score</th><th>Pick</th><th>Win chance</th><th>Fair moneyline</th><th>Line says</th><th>Line win chance</th><th class="lft">Adjusted for</th></tr></thead><tbody>' +
      gs.map(function (g) {
        var p = g.pred, homeFav = p.home_win >= 0.5, fav = homeFav ? g.home : g.away, w = homeFav ? p.home_win : 1 - p.home_win;
        var mk = p.market_home_pts == null ? '-' : esc(g.away) + ' ' + p.market_away_pts + ', ' + esc(g.home) + ' ' + p.market_home_pts;
        var mw = p.market_home_win == null ? '-' : (p.market_home_win >= 0.5 ? esc(g.home) + ' ' + pc(p.market_home_win) : esc(g.away) + ' ' + pc(1 - p.market_home_win));
        var notes = [[g.away, p.away_adj], [g.home, p.home_adj]].map(function (x) {
          var a = x[1]; if (!a || !a.minus) return '';
          var why = a.missing.slice(0, 3).map(esc); if (a.missing.length > 3) why.push('+' + (a.missing.length - 3) + ' more'); if (a.b2b) why.push('back-to-back');
          return esc(x[0]) + ' -' + a.minus + ' (' + why.join(', ') + ')';
        }).filter(Boolean).join('; ') || '-';
        return '<tr><td class="g lft">' + esc(g.away) + ' at ' + esc(g.home) + '</td><td>' + esc(g.away) + ' ' + p.away_pts + ', ' + esc(g.home) + ' ' + p.home_pts + '</td><td class="g">' + esc(fav) + ' by ' + Math.abs(p.margin).toFixed(1) +
          '</td><td>' + pc(w) + '</td><td>' + esc(g.away) + ' ' + ml(p.away_ml) + ' / ' + esc(g.home) + ' ' + ml(p.home_ml) + '</td><td>' + mk + '</td><td>' + mw + '</td><td class="lft" style="font-family:var(--body);font-size:.78rem;color:var(--muted);min-width:220px">' + notes + '</td></tr>';
      }).join('') + '</tbody></table></div><p class="lead" style="margin-top:10px">Projected score comes from each team\'s scoring and defense per possession, pace, and 2.5 points for home court. Points come off for rotation players who are out and for the second night of a back-to-back, shown under "Adjusted for". Fair moneyline is the win chance written as odds with no sportsbook fee. "Line says" is the score the posted spread and total imply.</p></section>';
  }
  function load(u) { return fetch(u, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }

  function gradeBlock(G) {
    if (!G) return '<section><div class="eyebrow">Last slate grade and record</div><p class="lead">No graded nights yet. This fills in the morning after the first projected slate.</p></section>';
    function rows(x) {
      return STATS.map(function (s) {
        var a = x.stats[s]; if (!a) return '';
        return '<tr><td class="pl">' + s + '</td><td>' + a.n + '</td><td>' + (a.bias > 0 ? '+' : '') + a.bias + '</td><td>' + a.mae + '</td><td>' + pc(a.floor_hit) +
          '</td><td>' + pc(a.blowout_floor_hit) + ' <span class="dim">(' + a.blowout_floor_n + ')</span></td><td>' + pc(a.rule_floor_hit_log) + '</td><td>' + pc(a.rule_floor_hit_flat) + '</td></tr>';
      }).join('');
    }
    function tbl(x) {
      return '<div class="tscroll"><table><thead><tr><th class="lft">Stat</th><th>Players</th><th>Avg miss</th><th>Avg abs miss</th><th>Floor hit</th><th>Blowout floor hit</th><th>Log rule</th><th>Flat rule</th></tr></thead><tbody>' + rows(x) + '</tbody></table></div>';
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
    return '<section><div class="eyebrow">Last slate grade and all-nights record</div><div class="grid2">' +
      '<div class="card"><h3>Last slate · ' + esc(L.date) + ' · ' + L.player_games + ' player-games</h3>' + tbl(L) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(L.star_floor_hit) + ' of ' + L.star_floors + ' held.</p>' +
      '<p><b>Star minutes.</b> ' + mins(L) + '</p><p><b>Blowout calls.</b> ' + calls + '</p>' +
      gp(L) + '<p><b>Projected but did not play (' + L.did_not_play.length + '):</b> ' + (L.did_not_play.map(esc).join(', ') || 'none') + '</p></div></div>' +
      '<div class="card"><h3>All nights · ' + A.nights + ' nights · ' + A.player_games + ' player-games</h3>' + tbl(A) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(A.star_floor_hit) + ' of ' + A.star_floors + ' held. The target is about 80%.</p>' +
      '<p><b>Star minutes.</b> ' + mins(A) + '</p><p><b>Games decided by 20 or more, by tag.</b> ' + tags(A) + '</p>' +
      '<p><b>Over-chance check.</b> ' + over(A) + '</p>' + gp(A) + '</div></div></div></section>';
  }

  function blowoutBoard(D) {
    var gs = D.games.slice().sort(function (a, b) { return b.p_blowout - a.p_blowout; });
    return '<section><div class="eyebrow">Blowout board</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Game</th><th>Spread</th><th>Total</th><th>Blowout risk</th><th>Tag</th></tr></thead><tbody>' +
      gs.map(function (g) {
        return '<tr><td class="g lft">' + esc(g.away) + ' at ' + esc(g.home) + '</td><td>' + spreadTxt(g) + '</td><td>' + dash(g.total) + '</td><td>' + pc(g.p_blowout) + '</td><td>' + tagEl(g.tag) + '</td></tr>';
      }).join('') + '</tbody></table></div><p class="lead" style="margin-top:10px">Blowout risk is the chance the final margin is 20 or more, from the spread. Stars lose minutes in those games.</p></section>';
  }

  function targets(D) {
    return '<section><div class="eyebrow">Target games by stat</div><div class="grid2">' + CEIL.map(function (s) {
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
    return '<section><div class="eyebrow">' + (anyLine ? 'Safest lines' : 'Steadiest floors') + '</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Player</th><th>Stat</th><th>Expected</th><th>Line</th><th>Over chance</th><th>Floor</th><th>Blowout floor</th></tr></thead><tbody>' +
      D.safest.map(function (r) {
        return '<tr><td class="g lft">' + esc(r.name) + ' <span class="date">' + esc(r.team) + '</span></td><td>' + r.stat + '</td><td>' + r.expected + '</td><td>' + dash(r.line) + '</td><td>' + pc(r.p_over) + '</td><td>' + r.floor + '</td><td>' + dash(r.blowout_floor) + '</td></tr>';
      }).join('') + '</tbody></table></div>' + (anyLine ? '' : '<p class="lead" style="margin-top:10px">No prop lines were loaded tonight, so these are the stars whose floor sits closest to their expected value.</p>') + '</section>';
  }

  function gameTable(g, anyLine) {
    var per = anyLine ? 4 : 2;
    var head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th>' + STATS.map(function (s) { return '<th class="grp" colspan="' + per + '">' + s + '</th>'; }).join('') + '</tr>' +
      '<tr><th></th><th></th><th></th>' + STATS.map(function () { return '<th class="grp">Exp</th><th>Floor</th>' + (anyLine ? '<th>Line</th><th>Over</th>' : ''); }).join('') + '</tr>';
    var cols = 3 + per * 4, body = '';
    g.teams.forEach(function (t) {
      var a = t.area;
      body += '<tr class="teamsplit"><td colspan="' + cols + '">' + esc(t.team) + ' vs ' + esc(t.opp) + ' defense · threes ' + rel(a.f3) + ' · paint ' + rel(a.fpaint) + ' · free throws ' + rel(a.fft) +
        (t.b2b ? ' · back-to-back' : '') + (t.out_scorers.length ? ' · out: ' + t.out_scorers.map(esc).join(', ') : '') + '</td></tr>';
      var bench = false;
      t.players.forEach(function (p) {
        if (p.role === 'bench' && !bench) { bench = true; body += '<tr class="benchrow"><td colspan="' + cols + '">Bench</td></tr>'; }
        body += '<tr' + (p.star ? ' class="hasub"' : '') + '><td class="pos">' + p.pos + '</td><td class="pl">' + esc(p.name) + (p.gtd ? '<span class="gtd">GTD</span>' : '') + '</td><td class="dim">' + p.min + '</td>' +
          STATS.map(function (s) {
            var x = p.stats[s];
            return '<td class="ex gl">' + x.expected + (x.check ? '<span class="chk">check</span>' : '') + '</td><td class="fl">' + x.floor + '</td>' + (anyLine ? '<td class="dim">' + dash(x.line) + '</td><td>' + pc(x.p_over) + '</td>' : '');
          }).join('') + '</tr>';
        if (p.star) body += '<tr><td class="sub"></td><td class="sub" colspan="2">normal / blowout / blowout floor</td>' +
          STATS.map(function (s) { var x = p.stats[s]; return '<td class="sub gl" colspan="' + per + '" style="text-align:right">' + x.normal + ' / ' + x.blowout + ' / ' + dash(x.blowout_floor) + '</td>'; }).join('') + '</tr>';
      });
    });
    var tip = new Date(g.tip).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET';
    return '<div class="game"><div class="ghead"><span class="ttl">' + esc(g.away) + ' at ' + esc(g.home) + '</span><div class="meta"><span class="pill">' + tip + '</span><span class="pill">' + spreadTxt(g) +
      '</span><span class="pill ou">O/U ' + dash(g.total) + '</span>' + tagEl(g.tag) + (g.locked ? '<span class="pill">locked at tip</span>' : '') + '</div></div><div class="tscroll"><table><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div></div>';
  }

  function ceiling(D) {
    return '<section><div class="eyebrow">Ceiling index</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Game</th>' + CEIL.map(function (s) { return '<th>' + s + '</th>'; }).join('') + '<th>Pace</th></tr></thead><tbody>' +
      D.games.map(function (g) {
        return '<tr><td class="g lft">' + esc(g.away) + ' at ' + esc(g.home) + '</td>' + CEIL.map(function (s) {
          var v = g.ceiling[s], flag = v != null && (v >= 1.08 || v <= 0.92);
          return '<td><span class="cv" style="' + (flag ? heat(v) : '') + '">' + (v == null ? '-' : v.toFixed(2)) + '</span></td>';
        }).join('') + '<td>' + g.pace.toFixed(2) + '</td></tr>';
      }).join('') + '</tbody></table></div><p class="lead" style="margin-top:10px">Shaded cells are 8% or more above or below an average game.</p></section>';
  }

  function method(D) {
    var m = D.method;
    return '<section><div class="eyebrow">Method</div><div class="method">' +
      '<p><b>Source.</b> Everything comes from ESPN box scores, odds and injury reports saved in this repo. Player rates, recent form, starters, defense by position (guard, forward, center), area defense (threes, paint, free throws) and pace are all built from those box scores.</p>' +
      '<p><b>History.</b> ' + m.history_days + ' game days, ' + esc(m.history_from) + ' to ' + esc(m.history_to) + '. ' + m.players + ' players projected. ' + m.log_floors + ' floors use the player\'s own game log and ' + m.flat_floors + ' use the flat rule.</p>' +
      '<p><b>Blowouts.</b> Final margins are assumed to land around the spread with a typical miss of ' + (m.sd || 13) + ' points. That was 13 until Nov 11, 2026, when 159 games this season showed blowouts happening more often than 13 allows. Tags: Low under 21%, Medium 21 to 27%, High over 27%.</p>' +
      '<p><b>Game predictions.</b> A missing rotation player costs his team half of what he scores beyond an average teammate in the same minutes, scaled down if the team has already played games without him. A back-to-back costs 1.5 points. On 108 replayed games these two adjustments did not measurably change accuracy, so treat them as reasonable assumptions that the nightly record will confirm or not.</p>' +
      '<p><b>Minutes swing.</b> Minutes are simulated with a night-to-night swing of 6 for bench players, 5 for starters under 18 points a game and 3 for stars. The first two match what the record shows. On the replay that moved bench points floors from 70% to 74% held and non-star starter floors from 76% to 79%.</p>' +
      '<p><b>Missing teammates.</b> When a 15-point scorer is out, each teammate\'s points rate is adjusted by how he has actually scored in games without that player, compared with his season rate, so a long absence is not counted twice. With few such games the number stays close to a small default lift. Assists use the default lift only. On 98 replayed cases this was about even with the old flat 5% rule, so it is not yet proven better.</p>' +
      '<p><b>Runs.</b> About 11:30am, 2:30pm, 5:37pm and 6:27pm ET. A game that has tipped keeps the numbers from the last run before tip' + (m.locked_games ? ' (' + m.locked_games + ' locked now)' : '') + '.</p>' +
      '<p><b>Lines.</b> ' + (m.lines_found ? m.lines_found + ' prop lines loaded. They never feed the projection.' : 'No prop lines loaded, so Line and Over chance are hidden.') + '</p>' +
      '<p><b>Limits.</b> Starters are taken from each team\'s last five games, not from tonight\'s posted lineup. Positions are ESPN\'s three groups. A late scratch after the run is not reflected.</p>' +
      '<p><b>Record.</b> Nights from Oct 30 to Nov 10, 2026 were replayed after the fact, each using only data from before that night. Later nights are graded live.</p>' +
      (m.notes.length ? '<p><b>Notes.</b> ' + m.notes.map(esc).join(' ') + '</p>' : '') + '</div></section>';
  }

  Promise.all([load('data/latest.json'), load('data/grade.json')]).then(function (r) {
    var D = r[0], G = r[1], app = document.getElementById('app');
    if (!D) { app.innerHTML = '<p class="empty">No projections yet. They appear after the first pregame run.</p>'; return; }
    document.getElementById('hdate').textContent = new Date(D.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) + ' · ' + D.games.length + ' games';
    document.getElementById('hrun').textContent = 'Run ' + D.run_time_et;
    var anyLine = D.method.lines_found > 0;
    app.innerHTML = (D.early_run ? '<div class="warnbar">Early run. Lineups are not final. Run again closer to tip.</div>' : '') +
      gradeBlock(G) + gamePreds(D) + blowoutBoard(D) + targets(D) + safest(D) +
      '<section><div class="eyebrow">Game by game</div><p class="lead" style="margin-bottom:14px">Exp is the expected value after blowout risk. Floor is the number reached in 80% of 10,000 simulated games.</p>' +
      D.games.map(function (g) { return gameTable(g, anyLine); }).join('') + '</section>' + ceiling(D) + method(D);
  });
})();
