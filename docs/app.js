// Renders docs/data/latest.json (tonight) and docs/data/grade.json (record).
// Both files are written by scripts/nightly.py. This page does no math of its own.
(function () {
  var STATS = ['PTS', 'REB', 'AST', '3PM'], CEIL = ['PTS', 'REB', 'AST', '3PM', 'STL', 'BLK'];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function dash(v) { return v == null || v === '' ? '-' : v; }
  function pc(v) { return v == null ? '-' : Math.round(v * 100) + '%'; }
  function rel(v) { var d = Math.round((v - 1) * 100); return (d > 0 ? '+' : '') + d + '%'; }
  function tagEl(t) { return '<span class="tag ' + (t || 'none') + '">' + (t || 'no line') + '</span>'; }
  function spreadTxt(g) { return g.favorite ? esc(g.favorite) : 'no spread'; }
  function heat(v) {
    if (v == null) return '';
    var d = v - 1, a = Math.min(0.5, Math.abs(d) * 4);
    return 'background:rgba(var(--' + (d >= 0 ? 'good' : 'bad') + '-rgb),' + a.toFixed(2) + ')';
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
      '<p><b>Projected but did not play (' + L.did_not_play.length + '):</b> ' + (L.did_not_play.map(esc).join(', ') || 'none') + '</p></div></div>' +
      '<div class="card"><h3>All nights · ' + A.nights + ' nights · ' + A.player_games + ' player-games</h3>' + tbl(A) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(A.star_floor_hit) + ' of ' + A.star_floors + ' held. The target is about 80%.</p>' +
      '<p><b>Star minutes.</b> ' + mins(A) + '</p><p><b>Games decided by 20 or more, by tag.</b> ' + tags(A) + '</p>' +
      '<p><b>Over-chance check.</b> ' + over(A) + '</p></div></div></div></section>';
  }

  function blowoutBoard(D) {
    var gs = D.games.slice().sort(function (a, b) { return b.p_blowout - a.p_blowout; });
    return '<section><div class="eyebrow">Blowout board</div><div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Game</th><th>Spread</th><th>Total</th><th>Blowout risk</th><th>Tag</th></tr></thead><tbody>' +
      gs.map(function (g) {
        return '<tr><td class="g lft">' + esc(g.away) + ' at ' + esc(g.home) + '</td><td>' + spreadTxt(g) + '</td><td>' + dash(g.total) + '</td><td>' + (g.spread == null ? '-' : pc(g.p_blowout)) + '</td><td>' + tagEl(g.tag) + '</td></tr>';
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
        (t.out_scorers.length ? ' · out: ' + t.out_scorers.map(esc).join(', ') : '') + '</td></tr>';
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
      '</span><span class="pill ou">O/U ' + dash(g.total) + '</span>' + tagEl(g.tag) + '</div></div><div class="tscroll"><table><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div></div>';
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
      gradeBlock(G) + blowoutBoard(D) + targets(D) + safest(D) +
      '<section><div class="eyebrow">Game by game</div><p class="lead" style="margin-bottom:14px">Exp is the expected value after blowout risk. Floor is the number reached in 80% of 10,000 simulated games.</p>' +
      D.games.map(function (g) { return gameTable(g, anyLine); }).join('') + '</section>' + ceiling(D) + method(D);
  });
})();
