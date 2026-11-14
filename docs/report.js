// Renders docs/data/report.json, which scripts/nightly.py rebuilds after every grade.
(function () {
  var STATS = ['PTS', 'REB', 'AST', '3PM'], NAME = { PTS: 'Points', REB: 'Rebounds', AST: 'Assists', '3PM': 'Threes' };
  var GROUPS = [['everyone', 'Everyone'], ['stars', 'Stars (18+ points a game)'], ['starters', 'Other starters'], ['bench', 'Bench']];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function pc(v) { return v == null ? '-' : Math.round(v * 100) + '%'; }
  function num(v, d) { return v == null ? '-' : Number(v).toFixed(d == null ? 1 : d); }
  function sg(v) { return v == null ? '-' : (v > 0 ? '+' : '') + Number(v).toFixed(2); }
  function bar(v) { return '<div class="bar"><i style="width:' + Math.round(Math.max(0, Math.min(1, v || 0)) * 100) + '%"></i></div>'; }
  function tone(v, lo, hi) { return v == null ? '' : (v < lo ? ' class="down"' : (v > hi ? ' class="warn"' : ' class="up"')); }
  function seg(id, items, cur) {
    return '<div class="seg" id="' + id + '">' + items.map(function (x) { return '<button type="button" data-v="' + x[0] + '" aria-pressed="' + (x[0] === cur) + '">' + x[1] + '</button>'; }).join('') + '</div>';
  }
  fetch('data/report.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }).then(function (R) {
    var app = document.getElementById('app');
    if (!R || !R.all) { app.innerHTML = '<p class="empty">No graded nights yet. The report fills in after the first morning grade.</p>'; return; }
    document.getElementById('hdate').textContent = 'Updated ' + R.generated_et;
    var scope = R.live && R.live.nights >= 3 ? 'live' : 'all', stat = 'PTS';
    try { var s0 = localStorage.getItem('rep-stat'); if (STATS.indexOf(s0) >= 0) stat = s0; } catch (e) {}
    function S() { return scope === 'last' ? R.last.scope : R[scope]; }
    function scopeLabel() {
      var x = S(); if (!x) return '';
      return scope === 'last' ? 'Last slate, ' + R.last.date : (scope === 'live' ? x.nights + ' live nights, ' + x.from + ' to ' + x.to : x.nights + ' nights (replayed and live), ' + x.from + ' to ' + x.to);
    }
    function reachTable(x) {
      return '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Group</th><th>Player-games</th><th>Reached expected</th><th>Reached or within 10%</th><th>Reached or within 20%</th><th>Reached or within ' + R.close[stat] + '</th><th>Fell 40%+ short</th><th>Avg expected</th><th>Avg actual</th><th>Avg miss</th></tr></thead><tbody>' +
        GROUPS.map(function (g) {
          var a = x.groups[g[0]]; if (!a) return '';
          return '<tr><td class="g lft">' + g[1] + '</td><td>' + a.n + '</td><td>' + pc(a.reached) + '</td><td>' + pc(a.within10) + '</td><td><b>' + pc(a.within20) + '</b></td><td>' + pc(a.close_abs) + '</td><td>' + pc(a.way_short) + '</td><td>' + num(a.avg_expected) + '</td><td>' + num(a.avg_actual) + '</td><td>' + num(a.mae, 2) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function ladder(x) {
      var steps = ['100', '90', '80', '70', '60', '50'];
      return '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Share of players who reached at least…</th>' + steps.map(function (k) { return '<th>' + k + '% of expected</th>'; }).join('') + '<th>Reached 4 times in 5</th><th>Reached 2 times in 3</th></tr></thead><tbody>' +
        GROUPS.map(function (g) {
          var a = x.groups[g[0]]; if (!a) return '';
          return '<tr><td class="g lft">' + g[1] + '</td>' + steps.map(function (k) { return '<td>' + pc(a.ladder[k]) + '</td>'; }).join('') + '<td><b>' + pc(a.reach80) + ' of expected</b></td><td>' + pc(a.reach67) + ' of expected</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function sizes(x) {
      return '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Expected ' + NAME[stat].toLowerCase() + '</th><th>Player-games</th><th>Reached expected</th><th>Reached or within 20%</th><th>Floor held</th><th>Avg miss</th><th>Runs high or low</th></tr></thead><tbody>' +
        x.by_size.filter(function (a) { return a.n; }).map(function (a) {
          return '<tr><td class="g lft">' + esc(a.label) + '</td><td>' + a.n + '</td><td>' + pc(a.reached) + '</td><td>' + pc(a.within20) + '</td><td>' + pc(a.floor_hit) + '</td><td>' + num(a.mae, 2) + '</td><td>' + (Math.abs(a.bias) < 0.25 ? 'about right' : (a.bias > 0 ? 'low by ' : 'high by ') + Math.abs(a.bias).toFixed(1)) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function floors(x) {
      return '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Group</th><th>Floor held (target 80%)</th><th>Floor held when his team lost by 20+</th><th>Blowout floor held when his team lost by 20+</th><th>Ceiling reached (meant to be about 10%)</th><th>Model miss</th><th>Season average miss</th></tr></thead><tbody>' +
        GROUPS.map(function (g) {
          var a = x.groups[g[0]]; if (!a) return '';
          return '<tr><td class="g lft">' + g[1] + '</td><td' + tone(a.floor_hit, 0.77, 0.86) + '>' + pc(a.floor_hit) + ' <span class="dim">(' + a.floor_hit_n + ')</span></td><td>' + pc(a.lost_floor) + ' <span class="dim">(' + a.lost_floor_n + ')</span></td><td>' + pc(a.lost_blowout_floor) + ' <span class="dim">(' + a.lost_blowout_floor_n + ')</span></td><td>' + pc(a.ceiling_hit) + ' <span class="dim">(' + a.ceiling_hit_n + ')</span></td><td>' + num(a.mae_same, 2) + '</td><td>' + num(a.naive_mae, 2) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function lines(L, label) {
      if (!L) return '<p class="note">No prop lines graded in this view yet. Lines started on Nov 13, 2026.</p>';
      return '<div class="tiles"><div class="tile"><div class="k">Lines graded, ' + label + '</div><div class="v">' + L.n + '</div><div class="s">' + pc(L.went_over) + ' went over</div></div>' +
        '<div class="tile"><div class="k">Avg miss: model vs line</div><div class="v">' + num(L.model_mae, 2) + ' vs ' + num(L.line_mae, 2) + '</div><div class="s">' + (L.model_mae < L.line_mae ? 'model closer on average' : 'line closer on average') + '</div></div>' +
        '<div class="tile"><div class="k">Model closer than the line</div><div class="v">' + pc(L.model_closer) + '</div><div class="s">50% would be even</div></div>' +
        '<div class="tile"><div class="k">Page leaned over (60%+)</div><div class="v">' + pc(L.lean_over.right) + '</div><div class="s">went over, of ' + L.lean_over.n + '</div></div>' +
        '<div class="tile"><div class="k">Page leaned under (40% or less)</div><div class="v">' + pc(L.lean_under.right) + '</div><div class="s">stayed under, of ' + L.lean_under.n + '</div></div></div>' +
        '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Over chance the page gave</th><th>Lines</th><th>Actually went over</th><th></th></tr></thead><tbody>' +
        L.buckets.map(function (b) { return '<tr><td class="g lft">' + b.bucket + '</td><td>' + b.n + '</td><td>' + pc(b.went_over) + '</td><td>' + bar(b.went_over) + '</td></tr>'; }).join('') +
        '</tbody></table></div><p class="note">If the over chances are honest, each row\'s "actually went over" lands inside its own range, rising from top to bottom. If it is flat or backwards, the over chance is not telling you anything the line does not already know.</p>';
    }
    function nights() {
      return '<div class="ceilwrap"><table class="ceil rt"><thead><tr><th class="lft">Night</th><th>Games</th><th>Players</th><th>Reached expected</th><th>Reached or within 20%</th><th>Floor held</th><th>Model miss</th><th>Season avg miss</th><th>Lines: model closer</th></tr></thead><tbody>' +
        R.nights.slice().reverse().map(function (n) {
          var a = n[stat]; if (!a) return '';
          return '<tr><td class="g lft">' + esc(n.date) + (n.live ? '<span class="livepill">live</span>' : '') + '</td><td>' + n.games + '</td><td>' + n.players + '</td><td>' + pc(a.reached) + '</td><td>' + pc(a.within20) + '</td><td' + tone(a.floor_hit, 0.72, 0.9) + '>' + pc(a.floor_hit) + '</td><td>' + num(a.mae, 2) + '</td><td>' + num(a.naive_mae, 2) + '</td><td>' + (n.lines ? pc(n.lines.model_closer) + ' <span class="dim">(' + n.lines.n + ')</span>' : '-') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function lastCards() {
      function tb(list, title) {
        return '<div class="card"><h3>' + title + '</h3><div class="tscroll"><table class="rt"><thead><tr><th class="lft">Player</th><th>Expected</th><th>Floor</th><th>Line</th><th>Actual</th><th>Minutes</th></tr></thead><tbody>' +
          list.map(function (c) { return '<tr><td class="pl">' + esc(c.player) + ' <span class="date">' + esc(c.team) + '</span></td><td>' + num(c.expected) + '</td><td>' + num(c.floor, 0) + '</td><td>' + (c.line == null ? '-' : c.line) + '</td><td class="ex">' + num(c.actual, 0) + '</td><td class="dim">' + num(c.minutes, 0) + ' <span class="dim">(' + num(c.proj_minutes, 0) + ')</span></td></tr>'; }).join('') +
          '</tbody></table></div></div>';
      }
      return '<div class="grid2 rgrid">' + tb(R.last.beats, 'Biggest beats, points · ' + esc(R.last.date)) + tb(R.last.misses, 'Biggest misses, points · ' + esc(R.last.date)) + '</div><p class="note">Minutes show what he played, with what was projected in brackets. Most big misses and beats come with a big minutes surprise.</p>';
    }
    function draw() {
      var x = S();
      if (!x) { scope = 'all'; x = S(); }
      var st = x.stats[stat], e = st.groups.everyone, stars = st.groups.stars;
      app.innerHTML =
        '<div class="rhead">' + seg('sc', [['live', 'Live nights'], ['all', 'All nights'], ['last', 'Last slate']].filter(function (v) { return v[0] !== 'live' || R.live; }), scope) + seg('ss', STATS.map(function (s) { return [s, NAME[s]]; }), stat) + '</div>' +
        '<p class="lead">' + esc(scopeLabel()) + ' · ' + x.player_games + ' player-games' + (scope === 'all' ? ' · nights before ' + esc(R.live_from) + ' were replayed after the fact' : '') + '</p>' +
        '<div class="tiles"><div class="tile"><div class="k">Reached the expected number</div><div class="v">' + pc(e.reached) + '</div><div class="s">about half is normal</div></div>' +
        '<div class="tile"><div class="k">Reached it or came within 20%</div><div class="v">' + pc(e.within20) + '</div><div class="s">stars: ' + pc(stars && stars.within20) + '</div></div>' +
        '<div class="tile"><div class="k">Floor held</div><div class="v">' + pc(e.floor_hit) + '</div><div class="s">target 80%</div></div>' +
        '<div class="tile"><div class="k">Reached 4 times in 5</div><div class="v">' + pc(e.reach80) + '</div><div class="s">of the expected number</div></div>' +
        '<div class="tile"><div class="k">Avg miss vs season average</div><div class="v">' + num(e.mae_same, 2) + ' vs ' + num(e.naive_mae, 2) + '</div><div class="s">' + (e.mae_same < e.naive_mae ? 'model closer' : 'season average closer') + '</div></div></div>' +
        '<p class="note"><b>How to read this.</b> The expected number is the middle of what the model thinks can happen, so a player lands above it about half the time and below it about half the time. That is what a fair projection looks like. The number built to be reached is the <b>floor</b>, which should hold about 4 times in 5. "Reached 4 times in 5" shows how much of the expected number players actually got to that often.</p>' +
        '<section><div class="eyebrow">Did players reach their expected ' + NAME[stat].toLowerCase() + '?</div>' + reachTable(st) + '</section>' +
        '<section><div class="eyebrow">How much of the expected number can you count on?</div>' + ladder(st) + '<p class="note">Read a row left to right: the share of players who got to at least that much of their expected number. The last two columns turn it around: the share of the expected number that was reached 4 times in 5, and 2 times in 3.</p></section>' +
        '<section><div class="eyebrow">By size of the projection</div>' + sizes(st) + '</section>' +
        '<section><div class="eyebrow">Floors, ceilings and the season-average test</div>' + floors(st) + '</section>' +
        '<section><div class="eyebrow">Against the prop lines · ' + NAME[stat].toLowerCase() + '</div>' + lines(x.lines[stat], NAME[stat].toLowerCase()) + '</section>' +
        '<section><div class="eyebrow">Against the prop lines · all four stats together</div>' + lines(x.lines.all, 'all stats') + '</section>' +
        '<section><div class="eyebrow">Night by night · ' + NAME[stat].toLowerCase() + '</div>' + nights() + '</section>' +
        '<section><div class="eyebrow">Last slate</div>' + lastCards() + '</section>';
      document.getElementById('sc').addEventListener('click', function (ev) { var v = ev.target.getAttribute && ev.target.getAttribute('data-v'); if (v) { scope = v; draw(); } });
      document.getElementById('ss').addEventListener('click', function (ev) { var v = ev.target.getAttribute && ev.target.getAttribute('data-v'); if (v) { stat = v; try { localStorage.setItem('rep-stat', v); } catch (e2) {} draw(); } });
    }
    draw();
  });
})();
