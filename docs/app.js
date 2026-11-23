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
  function fairMl(p) { p = Math.max(0.01, Math.min(0.99, p)); return p >= 0.5 ? Math.round(-100 * p / (1 - p)) : Math.round(100 * (1 - p) / p); }
  function gamesGrid(D) {
    return '<section id="games"><div class="eyebrow">Tonight\'s games</div><div class="gcards">' + D.games.map(function (g) {
      var p = g.pred, rows = '', src = '', hasLine = p && p.market_home_pts != null && p.market_home_win != null;
      if (p) {
        var hw = hasLine ? p.market_home_win : p.home_win, hp = hasLine ? p.market_home_pts : p.home_pts, ap = hasLine ? p.market_away_pts : p.away_pts;
        var pickHome = hw >= 0.5;
        src = hasLine ? 'line' : 'model';
        rows = [[g.away, ap, 1 - hw, fairMl(1 - hw), !pickHome], [g.home, hp, hw, fairMl(hw), pickHome]].map(function (r) {
          return '<div class="gteam' + (r[4] ? ' pick' : '') + '"><span class="ab">' + esc(r[0]) + '</span><span class="sc">' + r[1].toFixed(1) + '</span><span class="wp">' + pc(r[2]) + '</span><span class="mlv">' + ml(r[3]) + '</span></div>';
        }).join('') + '<div class="winbar" title="win chance"><i style="width:' + Math.round((1 - hw) * 100) + '%"></i></div>';
      }
      var line = g.favorite ? 'Line ' + esc(g.favorite) + (g.total != null ? ' · O/U ' + g.total : '') : 'No line posted';
      var model = '';
      if (p && hasLine) {
        var d = p.margin + g.spread;   // model margin minus line margin, home side
        model = 'Model: ' + esc(g.away) + ' ' + p.away_pts + ', ' + esc(g.home) + ' ' + p.home_pts + (Math.abs(d) >= 3 ? ' (' + Math.abs(d).toFixed(1) + ' off the line)' : '');
      }
      var adj = adjNote(g);
      return '<a class="gc" href="#g-' + g.game_id + '"><div class="gtop"><span class="gtime">' + tipTxt(g) + (g.locked ? ' · locked' : '') + '</span>' + tagEl(g.tag) + '</div>' +
        (p ? '<div class="ghdr"><span class="src">' + src + '</span><span>score</span><span>win</span><span>fair ML</span></div>' : '') + rows +
        '<div class="gmeta">' + line + ' · blowout risk ' + pc(g.p_blowout) + '</div>' + (model ? '<div class="gmeta">' + model + '</div>' : '') +
        (adj ? '<div class="gmeta adj">Model adjusted: ' + adj + '</div>' : '') + '</a>';
    }).join('') + '</div><p class="lead" style="margin-top:12px">When a betting line is posted, the score and win chance shown are the ones the line implies, because the line has been more accurate than this page\'s own game model (see Record). The model\'s score sits underneath as a second opinion, and it is the main number only when no line is posted. When the two differed by 3 or more points, the line was closer about 2 times in 3. Fair ML is the win chance written as odds with no sportsbook fee. Blowout risk is a weak signal: games tagged Low still ended by 20 or more about 1 time in 5, and High about 1 in 3, so lean on the blowout floor. Tap a game to jump to its players.</p></section>';
  }

  // What the other team is missing tonight, as short notes for one stat. Notes only: these do not move any number.
  function oppNotes(t, s, pos) {
    var o = [], m = t.opp_missing || [];
    function has(role) { return m.some(function (x) { return x.role === role; }); }
    if (s === 'REB' && has('rebounder')) o.push(esc(t.opp) + ' top rebounder out');
    if (s === 'PTS' && has('stealer')) o.push(esc(t.opp) + ' steals leader out');
    if (s === 'PTS' && has('blocker') && pos !== 'G') o.push(esc(t.opp) + ' shot blocker out');
    if (s === 'PTS' && t.opp_tired) o.push(esc(t.opp) + ' on a back-to-back');
    return o;
  }
  function oppLine(t) {
    var m = t.opp_missing || [], bits = [];
    if (m.length) bits.push(esc(t.opp) + ' without ' + m.map(function (x) { return x.label + ' ' + esc(x.name.split(' ').slice(-1)[0]); }).join(', '));
    if (t.opp_tired) bits.push(esc(t.opp) + ' on a back-to-back, ' + esc(t.team) + ' rested');
    return bits.join(' · ');
  }
  // Position matchups. SOFT/TOUGH are raw gaps in what a defense has allowed to a position.
  // Checked on 1,419 player-games (Oct 30 to Nov 11, 2026): about a fifth of the raw gap
  // carried over. Points rose against soft spots but did not fall against tough ones, and
  // threes showed no pattern by position, so those are not flagged.
  var SOFT = 1.12, TOUGH = 0.88, MSTATS = ['PTS', 'REB', 'AST'], TSTATS = ['PTS', 'REB', 'AST', '3PM'], PNAME = { G: 'Guards', F: 'Forwards', C: 'Centers' }, MINV = { PTS: 8, REB: 4, AST: 3 };
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
          var pl = b.t.players.filter(function (p) { return p.pos === pos && p.stats[s].expected >= MINV[s]; }).sort(function (x, y) { return y.stats[s].expected - x.stats[s].expected; });
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
    function absCard(bl) {
      var EFFECT = { rebounder: 'rebounds and paint points lean up', blocker: 'paint points lean up', stealer: 'points lean up, fewer turnovers', playmaker: 'slower game, slightly fewer chances for both teams' };
      var items = [];
      bl.forEach(function (b) {
        (b.t.opp_missing || []).forEach(function (x) { items.push('<a class="tg mlink" href="#g-' + b.g.game_id + '"><div class="g">' + esc(b.t.opp) + ' without ' + esc(x.name) + '</div><div class="m">' + x.label + '</div><div class="p">For ' + esc(b.t.team) + ': ' + EFFECT[x.role] + '</div></a>'); });
        if (b.t.opp_tired) items.push('<a class="tg mlink" href="#g-' + b.g.game_id + '"><div class="g">' + esc(b.t.opp) + ' on a back-to-back</div><div class="m">' + esc(b.t.team) + ' is rested</div><div class="p">For ' + esc(b.t.team) + ': points lean up</div></a>');
      });
      return '<div class="card"><h3>Key absences and rest</h3><div class="body">' + (items.length ? items.join('') : '<div class="tg"><div class="p">No top rebounder, shot blocker, steals leader or lead playmaker is out tonight, and no team is tired against a rested one.</div></div>') + '</div></div>';
    }
    function card(title, list, empty) {
      return '<div class="card"><h3>' + title + '</h3><div class="body">' + (list.length ? list.map(item).join('') : '<div class="tg"><div class="p">' + empty + '</div></div>') + '</div></div>';
    }
    var tbl = '<div class="ceilwrap" style="margin-top:12px"><table class="ceil"><thead><tr><th class="lft" rowspan="2">Defense</th>' + TSTATS.map(function (s) { return '<th class="grp" colspan="3">' + s + ' allowed</th>'; }).join('') + '</tr><tr>' +
      TSTATS.map(function () { return '<th class="grp">G</th><th>F</th><th>C</th>'; }).join('') + '</tr></thead><tbody>' +
      blocks.map(function (b) {
        return '<tr><td class="g lft">' + esc(b.t.opp) + ' <span class="date">vs ' + esc(b.t.team) + '</span></td>' + TSTATS.map(function (s) {
          return ['G', 'F', 'C'].map(function (pos, i) { var v = b.t.dvp[pos][s], k = spot(b.t, pos, s); return '<td' + (i ? '' : ' class="gl"') + '><span class="cv" style="' + (Math.abs(v - 1) >= 0.12 ? heat(v) : '') + '">' + rel(v) + '</span>' + mark(k) + '</td>'; }).join('');
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
    return '<section id="matchups"><div class="eyebrow">Position matchups</div><div class="grid2">' +
      card('▲ Soft spots tonight', soft, 'No defense tonight has been 12% or more above average against a position.') +
      card('▼ Tough spots tonight', tough, 'No defense tonight has been 12% or more below average against a position in rebounds or assists.') + absCard(blocks) + '</div>' + tbl +
      '<p class="lead" style="margin-top:10px">Percentages are what each defense has allowed to that position so far, against the league average. They are small samples, so read them as a lean. On 1,419 player-games this season about a fifth of the gap carried over to the next game: a defense that had allowed 25% more to a position meant about 5% more for the next player there. Key absences and rest come from two full seasons, each team compared with itself: with the steals leader out the other team scored 1.6 more points, with the top rebounder out it grabbed 1.8 more rebounds and scored 2.2 more in the paint, with the shot blocker out 1.8 more in the paint, and a tired team against a rested one gave up 1.5 more points. Those are whole-team numbers split across about nine players, and they are notes only: they do not change any projection. A missing scorer did not help the other team at all. Points rose against soft spots but did not fall against tough ones, so tough spots are not flagged for points. Threes are in the table but not flagged: so far neither a defense\'s record against a position nor its threes allowed overall has carried over to the next game. The Record section tracks all four stats every night, so this will show if a pattern appears. The projections already include position defense at the strength the record supports.</p></section>';
  }
  function mcheck(x) {
    var m = x.matchup_check; if (!m || !Object.keys(m).length) return '';
    function cell(c) { return c && c.ratio != null ? '<td><span class="cv" style="' + (Math.abs(c.ratio - 1) >= 0.05 ? heat(c.ratio) : '') + '">' + rel(c.ratio) + '</span> <span class="dim">(' + c.n + ')</span></td>' : '<td>-</td>'; }
    var names = { PTS: 'Points', REB: 'Rebounds', AST: 'Assists', '3PM': 'Threes, by position', '3PM_team': 'Threes, team defense' };
    return '<div class="tscroll" style="border-top:1px solid var(--border)"><table><thead><tr><th class="lft">Matchup check</th><th>Tough</th><th>Middle</th><th>Soft</th></tr></thead><tbody>' +
      ['PTS', 'REB', 'AST', '3PM', '3PM_team'].filter(function (k) { return m[k]; }).map(function (k) {
        return '<tr><td class="pl">' + names[k] + '</td>' + cell(m[k].tough) + cell(m[k].middle) + cell(m[k].soft) + '</tr>';
      }).join('') + '</tbody></table></div><div class="body"><p>How players did against their own usual rate, grouped by how the defense had done against their position (12% or more below or above average; 8% for team threes). If matchups matter, Soft should sit above Middle and Tough below it.</p></div>';
  }
  // the blowout floor shown is the blown-out version when there is one: it assumes his team is the one losing big
  function bfl(x) { return x.loss_floor != null ? x.loss_floor : x.blowout_floor; }
  // Hot and in a good spot: a streak where nothing about tonight's opponent should pull him down.
  // Leans: a side on a posted prop line, logged before tip and graded the next morning.
  function leansBlock(D, G) {
    var L = D.leans || [], R = (G && G.leans) || null, src = R ? R.sources : {};
    var names = { claude: 'Claude', 'rule:model_edge': 'Model vs line', 'rule:hot_spot': 'Hot + good spot', 'rule:fill_in': 'Fill-in starter', 'rule:big_dog_star': 'Star on big underdog' };
    var order = ['claude', 'rule:hot_spot', 'rule:fill_in', 'rule:big_dog_star', 'rule:model_edge'];
    var be = R ? R.breakeven : 0.524;
    var rec = '<div class="ceilwrap"><table class="ceil"><thead><tr><th class="lft">Source</th><th>W-L</th><th>Win %</th><th>Units at -110</th><th>Nights</th></tr></thead><tbody>' +
      order.concat(['all rules']).filter(function (k) { return src[k]; }).map(function (k) {
        var v = src[k], wr = v.win_rate;
        return '<tr><td class="lft">' + esc(names[k] || k) + '</td><td>' + v.win + '-' + v.loss + (v.push ? '-' + v.push : '') + '</td><td><span class="' + (wr != null && wr >= be ? 'up' : '') + '">' + pc(wr) + '</span></td><td>' + (v.units > 0 ? '+' : '') + v.units + '</td><td>' + v.nights + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    if (!Object.keys(src).length) rec = '<p class="lead">No graded leans yet. The record starts the morning after the first logged slate.</p>';
    var tonight = order.map(function (k) {
      var l = L.filter(function (x) { return x.source === k; });
      if (!l.length) return '';
      return '<div class="card"><h3>' + esc(names[k] || k) + ' <span class="dim">(' + l.length + ')</span></h3><div class="body">' + l.map(function (x) {
        return '<a class="tg mlink" href="#g-' + x.game_id + '"><div class="g">' + esc(x.player) + ' <span class="date">' + esc(x.team) + '</span> <span class="ceilv">' + (x.side === 'over' ? 'Over ' : 'Under ') + x.line + ' ' + x.stat + '</span></div><div class="p">' + esc(x.reason) + '</div></a>';
      }).join('') + '</div></div>';
    }).join('');
    var rules = R && R.rules ? '<p class="lead" style="margin-top:10px">' + Object.keys(R.rules).map(function (k) { return '<b>' + esc(names[k] || k) + '.</b> ' + esc(R.rules[k]); }).join(' ') + ' Claude leans are written by hand before tip.</p>' : '';
    return '<section id="leans"><div class="eyebrow">Leans</div>' +
      '<p class="lead">Each lean is a side on a posted line, logged before tip and graded the next morning. Breaking even at -110 takes ' + (be * 100).toFixed(1) + '%. Tracking only, not betting advice: judge a source after a couple hundred graded leans, not a few nights.</p>' +
      rec + (tonight ? '<div class="grid2" style="margin-top:12px">' + tonight + '</div>' : '<p class="lead" style="margin-top:12px">No leans for tonight\'s open games.</p>') + rules + '</section>';
  }
  function hotSpots(D) {
    var H = D.hot_spots; if (!H) return '';
    var names = { PTS: 'Points', REB: 'Rebounds', AST: 'Assists', '3PM': 'Threes' };
    var total = STATS.reduce(function (n, s) { return n + (H[s] || []).length; }, 0);
    var cards = STATS.map(function (s) {
      var l = H[s] || [];
      return '<div class="card"><h3>' + names[s] + '</h3><div class="body">' + (l.length ? l.map(function (x) {
        var plus = x.spot && x.spot.plus && x.spot.plus.length ? x.spot.plus.map(esc).join(' · ') : 'no drag from the matchup';
        return '<a class="tg mlink" href="#g-' + x.gid + '"><div class="g">' + esc(x.name) + ' <span class="date">' + esc(x.team) + '</span> <span class="ceilv">' + x.line + '+</span></div>' +
          '<div class="m"><span class="up">' + x.games + ' straight</span> · last 5: ' + x.last5.join(', ') + ' · model ' + pc(x.model) + (x.prop != null ? ' · prop ' + x.prop : '') + '</div>' +
          '<div class="p">Spot: ' + plus + '</div></a>';
      }).join('') : '<div class="tg"><div class="p">No streak in this stat has a clean spot tonight.</div></div>') + '</div></div>';
    }).join('');
    return '<section id="hotspots"><div class="eyebrow">Hot and in a good spot</div>' +
      (total ? '' : '<p class="lead">No streak tonight has a clean spot.</p>') + '<div class="grid2">' + cards + '</div>' +
      '<p class="lead" style="margin-top:10px">These are the streaks below where nothing about tonight\'s opponent is expected to pull him down. A streak is left out if the model\'s matchup cuts his projection 3% or more, if the defense has allowed 12% or more below average to his position in that stat, or if the game carries High blowout risk. A neutral matchup counts as a good spot. Pluses (a soft defense, a missing rebounder or shot blocker, a tired opponent) are shown but not required.</p></section>';
  }
  // Streaks: the highest ladder line each player has reached in every one of his last 5+ games.
  function streaks(D) {
    var S = D.streaks; if (!S) return '';
    var names = { PTS: 'Points', REB: 'Rebounds', AST: 'Assists', '3PM': 'Threes' };
    if (!STATS.some(function (s) { return (S[s] || []).length; })) return '';
    return '<section id="streaks"><div class="eyebrow">Streaks</div><div class="grid2">' + STATS.map(function (s) {
      var l = S[s] || [];
      return '<div class="card"><h3>' + names[s] + '</h3><div class="body">' + (l.length ? l.map(function (x) {
        return '<a class="tg mlink" href="#g-' + x.gid + '"><div class="g">' + esc(x.name) + ' <span class="date">' + esc(x.team) + '</span> <span class="ceilv">' + x.line + '+</span></div>' +
          '<div class="m"><span class="up">' + x.games + ' straight</span> · last 5: ' + x.last5.join(', ') + ' · season ' + x.season + '</div>' +
          '<div class="p">tonight: expected ' + x.expected + ' · model gives ' + x.line + '+ a ' + pc(x.model) + ' chance' + (x.prop != null ? ' · prop line ' + x.prop : '') + '</div>' +
          (x.spot ? '<div class="p">' + (x.spot.good ? '<span class="up">good spot</span>' : '<span class="down">tough spot: ' + x.spot.against.map(esc).join(', ') + '</span>') + '</div>' : '') + '</a>';
      }).join('') : '<div class="tg"><div class="p">No one on tonight\'s slate has a streak of 5+ games at a line worth listing.</div></div>') + '</div></div>';
    }).join('') + '</div><p class="lead" style="margin-top:10px">The big number is the highest ladder line he has reached in every one of his last 5 or more games (points 10, 15, 20, 25 and up; rebounds 4, 6, 8, 10; assists 3, 4, 6, 8; threes 1, 2, 3), listed when that line is at least half his season average. Longest streaks first. On this season\'s box scores, a streak meant more than his season numbers alone: among players who had cleared a line 70 to 85% of the time before their last 5 games, those on a streak cleared it next time 83% of the time against 66% for those who were not, and streaks of 10 or more games were cleared 89% of the time. Compare it with the model\'s chance: the model already counts recent games, so when both are high the case is stronger.</p></section>';
  }

  // Players who could go off: the highest ceilings tonight. A ceiling is the number reached in the best
  // 1 simulated game in 20 (on the replay, reached about 1 time in 10).
  function goOff(D) {
    var all = [];
    D.games.forEach(function (g) { g.teams.forEach(function (t) { t.players.forEach(function (p) { all.push({ g: g, t: t, p: p }); }); }); });
    if (!all.length || all[0].p.stats.PTS.ceiling == null && !all.some(function (x) { return x.p.stats.PTS.ceiling != null; })) return '';
    function why(x, s) {
      var o = [], st = x.p.stats[s];
      if (spot(x.t, x.p.pos, s) > 0) o.push('soft matchup');
      if ((s === 'PTS' || s === 'AST') && st.bump >= 1.03 && x.t.out_scorers.length) o.push(esc(x.t.out_scorers[0].split(' ').slice(-1)[0]) + ' out');
      oppNotes(x.t, s, x.p.pos).forEach(function (n) { o.push(n); });
      if (x.g.ceiling && x.g.ceiling[s] >= 1.05) o.push('target game');
      else if (x.g.pace >= 1.03) o.push('fast game');
      return o;
    }
    var names = { PTS: 'Points', REB: 'Rebounds', AST: 'Assists', '3PM': 'Threes' };
    return '<section id="ceilings"><div class="eyebrow">Could go off</div><div class="grid2">' + STATS.map(function (s) {
      var top = all.filter(function (x) { return x.p.stats[s].ceiling != null; }).sort(function (a, b) { return b.p.stats[s].ceiling - a.p.stats[s].ceiling || b.p.stats[s].expected - a.p.stats[s].expected; }).slice(0, 6);
      return '<div class="card"><h3>' + names[s] + '</h3><div class="body">' + top.map(function (x) {
        var st = x.p.stats[s], w = why(x, s);
        return '<a class="tg mlink" href="#g-' + x.g.game_id + '"><div class="g">' + esc(x.p.name) + ' <span class="date">' + esc(x.t.team) + '</span> <span class="ceilv">' + st.ceiling + '</span></div>' +
          '<div class="m">expected ' + st.expected + (st.line != null ? ' · line ' + st.line : '') + (w.length ? ' · <span class="up">' + w.join(', ') + '</span>' : '') + '</div></a>';
      }).join('') + '</div></div>';
    }).join('') + '</div><p class="lead" style="margin-top:10px">The big number is the ceiling: what he reaches in his best 1 game in 20 according to the simulation. On the replay that was reached about 1 time in 10 for points, rebounds and assists (threes run higher because they come in whole numbers). Ranking by ceiling does find the big games: the top tenth of ceilings produced 35 of the 60 games of 30 or more points. The green notes are leans, not guarantees. Ranking players by how far their ceiling sits above their expected value did not pick out who goes off, so the page does not do that.</p></section>';
  }
  function load(u) { return fetch(u, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }

  function gradeBlock(G) {
    if (!G) return '<section id="record"><div class="eyebrow">Last slate grade and record</div><p class="lead">No graded nights yet. This fills in the morning after the first projected slate.</p></section>';
    function rows(x) {
      return STATS.map(function (s) {
        var a = x.stats[s]; if (!a) return '';
        return '<tr><td class="pl">' + s + '</td><td>' + a.n + '</td><td>' + (a.bias > 0 ? '+' : '') + a.bias + '</td><td>' + a.mae + '</td><td class="dim">' + pc(a.ceiling_hit) + '</td><td class="dim">' + (a.naive_mae == null ? '-' : a.naive_mae.toFixed(2)) + '</td><td>' + pc(a.floor_hit) +
          '</td><td>' + pc(a.floor_hit_full) + '</td><td>' + pc(a.blowout_floor_hit) + ' <span class="dim">(' + a.blowout_floor_n + ')</span></td><td>' + pc(a.rule_floor_hit_log) + '</td><td>' + pc(a.rule_floor_hit_flat) + '</td></tr>';
      }).join('');
    }
    function tbl(x) {
      return '<div class="tscroll"><table><thead><tr><th class="lft">Stat</th><th>Players</th><th>Avg miss</th><th>Avg abs miss</th><th title="How often the ceiling was reached. Since 2026-11-19 it is meant to be about 1 time in 10.">Ceiling reached</th><th title="Average miss if you had just used each player\'s season average">Season avg miss</th><th>Floor hit</th><th title="Leaving out players who left early">Full games</th><th>Blowout floor hit</th><th>Log rule</th><th>Flat rule</th></tr></thead><tbody>' + rows(x) + '</tbody></table></div>';
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
    function tcheck(x) {
      var t = x.threes_check; if (!t || !Object.keys(t).length) return '';
      var cols = ['under 30%', '30 to 50%', '50 to 70%', '70 to 85%', '85% and up'];
      return '<div class="tscroll" style="border-top:1px solid var(--border)"><table><thead><tr><th class="lft">Threes check</th>' + cols.map(function (c) { return '<th>' + c + '</th>'; }).join('') + '</tr></thead><tbody>' +
        ['1', '2', '3'].filter(function (k) { return t[k]; }).map(function (k) {
          var by = {}; t[k].forEach(function (b) { by[b.bucket] = b; });
          return '<tr><td class="pl">Made ' + k + ' or more</td>' + cols.map(function (c) { return by[c] ? '<td>' + pc(by[c].made) + ' <span class="dim">(' + by[c].n + ')</span></td>' : '<td>-</td>'; }).join('') + '</tr>';
        }).join('') + '</tbody></table></div><div class="body"><p>Columns are the chance the page gave. Cells are how often it happened. They should land inside their column.</p></div>';
    }
    function score(x, label) {
      function chip(name, val, verdict, cls) { return '<div class="scd"><div class="scn">' + name + '</div><div class="scv">' + val + '</div><div class="scj ' + cls + '">' + verdict + '</div></div>'; }
      function fl(v) { return v == null ? ['-', 'none'] : (v < 0.77 ? ['running low', 'down'] : (v > 0.84 ? ['cautious', 'warn'] : ['on target', 'up'])); }
      var out = '', sf = fl(x.star_floor_hit), p = x.stats.PTS || {}, af = fl(p.floor_hit);
      out += chip('Star points floors', pc(x.star_floor_hit), sf[0], sf[1]);
      out += chip('All points floors', pc(p.floor_hit), af[0], af[1]);
      if (p.naive_mae != null) {
        var d = (p.model_mae_same - p.naive_mae) / p.naive_mae;
        out += chip('Points miss vs season average', p.model_mae_same.toFixed(2) + ' vs ' + p.naive_mae.toFixed(2), d < -0.02 ? 'model is better' : (d > 0.02 ? 'season average is better' : 'about even'), d < -0.02 ? 'up' : (d > 0.02 ? 'down' : 'warn'));
      }
      var g = x.game_preds;
      if (g && g.market_winner_hit != null) {
        var dd = g.winner_hit - g.market_winner_hit;
        out += chip('Winners: model vs line', pc(g.winner_hit) + ' vs ' + pc(g.market_winner_hit), dd > 0.03 ? 'model ahead' : (dd < -0.03 ? 'line ahead' : 'about even'), dd > 0.03 ? 'up' : (dd < -0.03 ? 'down' : 'warn'));
      }
      return '<div class="scwrap"><div class="scl">' + label + '</div><div class="scards">' + out + '</div></div>';
    }
    var L = G.last, A = G.all, V = G.live;
    var useLive = V && V.nights >= 5;
    var liveCard = V ? '<div class="card"><h3>Live nights · ' + V.nights + ' since ' + esc(G.live_from) + ' · ' + V.player_games + ' player-games</h3>' + tbl(V) + '<div class="body">' +
      '<p>Only slates projected before tip by the scheduled runs, with the settings frozen. This is the record to trust.</p>' +
      '<p><b>Star points floors:</b> ' + pc(V.star_floor_hit) + ' of ' + V.star_floors + ' held.</p>' + gp(V) + '</div></div>'
      : '<div class="card"><h3>Live nights</h3><div class="body"><p>Starts with the first slate graded after ' + esc(G.live_from || '') + '. Only slates projected before tip by the scheduled runs count here, with the settings frozen. Until then the record below is mostly replayed nights.</p></div></div>';
    var calls = L.blowout_calls.map(function (c) { return esc(c.game) + ' ' + pc(c.p_blowout) + ' → final margin ' + c.margin; }).join(' · ');
    return '<section id="record"><div class="eyebrow">Record</div>' + score(useLive ? V : A, useLive ? 'Scorecard, live nights' : 'Scorecard, all ' + A.nights + ' nights (mostly replayed)') + '<div class="grid2 rgrid">' +
      '<div class="card"><h3>Last slate · ' + esc(L.date) + ' · ' + L.player_games + ' player-games</h3>' + tbl(L) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(L.star_floor_hit) + ' of ' + L.star_floors + ' held' + (L.left_early_n ? ', or ' + pc(L.star_floor_hit_full) + ' of ' + L.star_floors_full + ' leaving out players who left early' : '') + '.</p>' +
      (L.left_early && L.left_early.length ? '<p><b>Left early (' + L.left_early.length + '):</b> ' + L.left_early.map(esc).join(', ') + '. Starters who played under half their projected minutes in a game that was not a blowout, usually an injury.</p>' : '') +
      '<p><b>Star minutes.</b> ' + mins(L) + '</p><p><b>Blowout calls.</b> ' + calls + '</p>' +
      gp(L) + '<p><b>Projected but did not play (' + L.did_not_play.length + '):</b> ' + (L.did_not_play.map(esc).join(', ') || 'none') + '</p></div></div>' + liveCard +
      '<div class="card"><h3>All nights, replayed and live · ' + A.nights + ' nights · ' + A.player_games + ' player-games</h3>' + tbl(A) + '<div class="body">' +
      '<p><b>Star points floors:</b> ' + pc(A.star_floor_hit) + ' of ' + A.star_floors + ' held' + (A.left_early_n ? ', or ' + pc(A.star_floor_hit_full) + ' of ' + A.star_floors_full + ' leaving out the ' + A.left_early_n + ' players who left early' : '') + '. The target is about 80%.</p>' +
      (A.star_blowout_sides && A.star_blowout_sides.lost_floor ? '<p><b>Stars in blowouts, by side.</b> Team won by 20 or more: floor held ' + pc(A.star_blowout_sides.won_floor.hit) + ' of ' + A.star_blowout_sides.won_floor.n + '. Team lost by 20 or more: floor held ' + pc(A.star_blowout_sides.lost_floor.hit) + ' of ' + A.star_blowout_sides.lost_floor.n + (A.star_blowout_sides.lost_loss_floor ? ', blowout floor held ' + pc(A.star_blowout_sides.lost_loss_floor.hit) + ' of ' + A.star_blowout_sides.lost_loss_floor.n : '') + '.</p>' : '') +
      '<p><b>Star minutes.</b> ' + mins(A) + '</p><p><b>Games decided by 20 or more, by tag.</b> ' + tags(A) + '</p>' +
      '<p><b>Over-chance check.</b> ' + over(A) + '</p>' + gp(A) + '</div>' + mcheck(A) + tcheck(A) + '</div></div></section>';
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
        return '<tr><td class="g lft">' + esc(r.name) + ' <span class="date">' + esc(r.team) + '</span></td><td>' + r.stat + '</td><td>' + r.expected + '</td><td>' + dash(r.line) + '</td><td>' + pc(r.p_over) + '</td><td>' + r.floor + '</td><td>' + dash(bfl(r)) + '</td></tr>';
      }).join('') + '</tbody></table></div>' + (anyLine ? '' : '<p class="lead" style="margin-top:10px">No prop lines were loaded tonight, so these are the stars whose floor sits closest to their expected value.</p>') + '</section>';
  }

  function gameTable(g, anyLine, mode) {
    var all = mode === 'ALL', head, cols, body = '';
    if (all) {
      var per = anyLine ? 4 : 2;
      head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th>' + STATS.map(function (s) { return '<th class="grp" colspan="' + per + '">' + s + '</th>'; }).join('') + '</tr>' +
        '<tr><th></th><th></th><th></th>' + STATS.map(function (s) { return '<th class="grp">Exp</th><th' + (s === '3PM' ? ' title="Chance of at least one three">1+' : '>Floor') + '</th>' + (anyLine ? '<th>Line</th><th>Over</th>' : ''); }).join('') + '</tr>';
      cols = 3 + per * 4;
    } else if (mode === '3PM') {
      head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th><th>Season</th><th>Expected</th><th>1 or more</th><th>2 or more</th><th>3 or more</th><th>Normal game</th><th>Blowout game</th>' + (anyLine ? '<th>Line</th><th>Over chance</th>' : '') + '</tr>';
      cols = 10 + (anyLine ? 2 : 0);
    } else {
      head = '<tr><th class="lft">Pos</th><th class="lft">Player</th><th>Min</th><th>Season</th><th>Expected</th><th>Floor</th><th>Blowout floor</th><th>Ceiling</th><th>Normal game</th><th>Blowout game</th><th>Matchup</th>' + (anyLine ? '<th>Line</th><th>Over chance</th>' : '') + '</tr>';
      cols = 11 + (anyLine ? 2 : 0);
    }
    g.teams.forEach(function (t) {
      var a = t.area;
      body += '<tr class="teamsplit"><td colspan="' + cols + '">' + esc(t.team) + ' <span class="vs">vs ' + esc(t.opp) + ' defense: threes ' + rel(a.f3) + ', paint ' + rel(a.fpaint) + ', free throws ' + rel(a.fft) +
        (oppLine(t) ? ' · <span class="up">' + oppLine(t) + '</span>' : '') + (t.b2b ? ' · back-to-back' : '') + (t.out_scorers.length ? ' · out: ' + t.out_scorers.map(esc).join(', ') : '') + '</span></td></tr>';
      var bench = false;
      t.players.forEach(function (p) {
        if (p.role === 'bench' && !bench) { bench = true; body += '<tr class="benchrow"><td colspan="' + cols + '">Bench</td></tr>'; }
        var nm = '<td class="pos">' + p.pos + '</td><td class="pl">' + esc(p.name) + (p.star ? '<span class="starmk" title="18 or more points a game">★</span>' : '') + (p.gtd ? '<span class="gtd">GTD</span>' : '') + '</td><td class="dim">' + p.min + '</td>';
        var key = ' data-n="' + esc(p.name.toLowerCase()) + '"';
        if (all) {
          body += '<tr class="prow' + (p.star ? ' hasub' : '') + '"' + key + '>' + nm + STATS.map(function (s) {
            var x = p.stats[s];
            return '<td class="ex gl">' + mark(spot(t, p.pos, s)) + x.expected + (x.check ? '<span class="chk">check</span>' : '') + '</td><td class="fl">' + (s === '3PM' ? (x.at_least ? pc(x.at_least['1']) : '-') : x.floor) + '</td>' + (anyLine ? '<td class="dim">' + dash(x.line) + '</td><td>' + pc(x.p_over) + '</td>' : '');
          }).join('') + '</tr>';
          if (p.star) body += '<tr class="prow"' + key + '><td class="sub"></td><td class="sub" colspan="2">normal / blowout / blowout floor</td>' +
            STATS.map(function (s) { var x = p.stats[s]; return '<td class="sub gl" colspan="' + per + '" style="text-align:right">' + x.normal + ' / ' + x.blowout + ' / ' + dash(bfl(x)) + '</td>'; }).join('') + '</tr>';
        } else if (mode === '3PM') {
          var y = p.stats['3PM'], al = y.at_least || {};
          body += '<tr class="prow"' + key + '>' + nm + '<td class="dim">' + p.season['3PM'] + '</td><td class="ex">' + y.expected + '</td>' + ['1', '2', '3'].map(function (k) { return '<td class="fl">' + (al[k] == null ? '-' : pc(al[k])) + '</td>'; }).join('') +
            '<td class="dim">' + y.normal + '</td><td class="dim">' + y.blowout + '</td>' + (anyLine ? '<td class="dim">' + dash(y.line) + '</td><td>' + pc(y.p_over) + '</td>' : '') + '</tr>';
        } else {
          var x = p.stats[mode], m = x.matchup == null ? null : x.matchup * (x.bump || 1);
          body += '<tr class="prow"' + key + '>' + nm + '<td class="dim">' + p.season[mode] + '</td><td class="ex">' + mark(spot(t, p.pos, mode)) + x.expected + (x.check ? '<span class="chk">check</span>' : '') + '</td><td class="fl">' + x.floor + '</td><td class="fl">' + dash(bfl(x)) +
            '</td><td class="cl">' + dash(x.ceiling) + '</td><td class="dim">' + x.normal + '</td><td class="dim">' + x.blowout + '</td><td class="' + (m == null || Math.abs(m - 1) < 0.03 ? 'dim' : (m > 1 ? 'up' : 'down')) + '">' + (m == null ? '-' : rel(m)) + '</td>' +
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
      '<p><b>Frozen settings.</b> The model\'s settings were frozen on ' + esc(D.model || 'Nov 12, 2026') + '. They stay put until 15 live nights are graded, and a change then has to hold up on the live record as well as the replay.</p>' +
      '<p><b>Last season.</b> Each player\'s per-minute rates and minutes are blended with last season\'s, counted as about 100 minutes and 3 games of evidence, so the blend fades as this season\'s sample grows. Team ratings for the game margin are blended the same way. On the replay this was the first change to beat a plain season average on all four stats. It was switched on the night of Nov 12, so the Nov 12 slate was projected without it.</p>' +
      '<p><b>Bench points floors.</b> Bench players\' points floors use the number reached in 88% of simulated games, not 80%. With the usual rule they held 74% of the time on the replay, and with this one 81%. Their minutes are less predictable than starters\'.</p>' +
      '<p><b>Tested and left out.</b> Making each team\'s minutes add up to 240, opponent-adjusted team ratings, and heavier or lighter weight on recent form were all tested on the replay and did not reduce the miss.</p>' +
      '<p><b>Threes.</b> Three-point projections use the player\'s own rate, minutes and game pace. They are not adjusted for the opposing defense, because so far this season neither threes allowed overall nor threes allowed to a position has carried over to the next game. The matchup check in the Record section tracks this every night.</p>' +
      '<p><b>Blowout floor.</b> Two seasons of games (32,000 player performances) show that a blowout win barely hurts a star: he loses minutes but scores 93 to 98% of his usual points. A blowout loss is what hurts: stars scored 77 to 80% of usual and had a bad night twice as often. So the blowout floor on this page assumes his team is the one losing big, with the measured drop in minutes and scoring applied. On the replay it held for stars in 74% of real blowout losses, against 40% for the regular floor. For players on heavy favorites there are too few losing runs to measure, and the older version (any blowout) is shown.</p>' +
      '<p><b>Blowout minutes.</b> In a blowout, players at 30 or more minutes are projected to keep 87% of their minutes, which is what the record measured. Floors use a more cautious 80%. With 87% in the floors, star blowout floors held 71% of the time on the replay, against 80% with the cautious number.</p>' +
      '<p><b>Blowouts.</b> Final margins are assumed to land around the spread with a typical miss of ' + (m.sd || 13) + ' points. That was 13 until Nov 11, 2026, when 159 games this season showed blowouts happening more often than 13 allows. Tags: Low under 21%, Medium 21 to 27%, High over 27%.</p>' +
      '<p><b>Game predictions.</b> A missing rotation player costs his team half of what he scores beyond an average teammate in the same minutes, scaled down if the team has already played games without him. A back-to-back costs 1.5 points. On 108 replayed games these two adjustments did not measurably change accuracy, so treat them as reasonable assumptions that the nightly record will confirm or not.</p>' +
      '<p><b>Minutes swing.</b> Minutes are simulated with a night-to-night swing of 6 for bench players, 5 for starters under 18 points a game and 3 for stars. The first two match what the record shows. On the replay that moved bench points floors from 70% to 74% held and non-star starter floors from 76% to 79%.</p>' +
      '<p><b>Missing teammates.</b> When a 15-point scorer is out, each teammate\'s points rate is adjusted by how he has actually scored in games without that player, compared with his season rate, so a long absence is not counted twice. With few such games the number stays close to a small default lift. Assists use the default lift only. On 98 replayed cases this was about even with the old flat 5% rule, so it is not yet proven better.</p>' +
      '<p><b>Runs.</b> About 11:30am, 2:30pm, 5:37pm and 6:27pm ET. A game that has tipped keeps the numbers from the last run before tip' + (m.locked_games ? ' (' + m.locked_games + ' locked now)' : '') + '.</p>' +
      '<p><b>Lines.</b> ' + (m.lines_found ? m.lines_found + ' prop lines loaded from ESPN\'s public odds feed (one sportsbook), matched by player id. Only pregame lines are saved. Since 2026-11-19, where a line exists the projection is one quarter the model and three quarters the line, because on the replay the line was the better projection (points off by 5.05 against 5.28 for the model). Over chance starts from the share of 10,000 simulated games that finished above the line, shrunk to a quarter of its lean, because the raw simulation spread far wider than what happened: players went over about half the time whatever it said. So over chances near 50% are the honest answer, and "check" marks a projection 20% or more away from its line, which is either a real gap or something the line knows that the model does not.' : 'No prop lines loaded for this slate, so Line and Over chance are hidden.') + '</p>' +
      '<p><b>Positions.</b> ESPN lists many centers as forwards. When a team starts no listed center, the starting forward who rebounds and blocks the most is treated as the center' + (m.centers_fixed && m.centers_fixed.length ? '. Currently: ' + m.centers_fixed.map(esc).join(', ') : '') + '.</p>' +
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
    var stale = '';
    if (D.run_utc) {
      var age = (Date.now() - Date.parse(D.run_utc)) / 3.6e6, open = D.games.filter(function (g) { return Date.parse(g.tip) > Date.now(); }).length;
      var todayEt = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
      if (open && age > 3) stale = '<div class="warnbar">These numbers are ' + Math.round(age) + ' hours old and ' + open + (open === 1 ? ' game has' : ' games have') + ' not tipped. Late injury news may be missing. To refresh now, open the repo\'s Actions tab, pick "NBA nightly projections" and click Run workflow.</div>';
      else if (!open && D.date < todayEt) stale = '<div class="warnbar">Showing ' + esc(D.date) + '. Today\'s games appear after the first run of the day.</div>';
    }
    app.innerHTML = stale + (D.early_run && !stale ? '<div class="warnbar">Early look. Injuries and spreads can still change. This page refreshes at about 2:31pm, 5:37pm and 6:27pm ET, and each game locks at its tip.</div>' : '') +
      gamesGrid(D) + matchups(D) + goOff(D) + hotSpots(D) + streaks(D) + targets(D) + safest(D) +
      '<section id="players"><div class="eyebrow">Players, game by game</div><div class="controls"><input id="q" type="search" placeholder="Find a player" aria-label="Find a player">' +
      '<div class="seg" id="seg" role="group" aria-label="Stat shown">' + ['ALL'].concat(STATS).map(function (s) { return '<button type="button" data-m="' + s + '">' + (s === 'ALL' ? 'All stats' : s) + '</button>'; }).join('') + '</div>' +
      '<button type="button" class="tgl" id="fold">Collapse all</button></div>' +
      '<p class="lead" style="margin-bottom:14px">Expected already accounts for blowout risk. Floor is the number reached in 80% of 10,000 simulated games. Blowout floor is the number reached in 80% of the simulated games where his team loses by 20 or more, which is the case that actually hurts. ★ marks players at 18 or more points a game. ▲ and ▼ mark a soft or tough position matchup for that stat. For threes the page shows the chance of making at least 1, 2 or 3, because a floor of 0 says little.</p>' +
      '<div id="tables"></div><p class="empty" id="nomatch" hidden>No player on tonight\'s slate matches that name.</p></section>' + ceiling(D) + leansBlock(D, G) + gradeBlock(G) + method(D);

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
