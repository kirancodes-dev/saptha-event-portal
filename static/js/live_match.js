/* Live match scoring and the live scoreboard (UPG-351).
 *
 * The scorer's page ([data-live-scorer]) sends each tap with its own id, one
 * at a time in order, so a tap retried on a weak connection counts once and
 * two quick taps never overwrite each other. The public scoreboard
 * ([data-live-board]) asks for the score every few seconds. Both tick the
 * clock locally between updates.
 */
(function () {
  'use strict';

  var POLL_MS = 1500;   // the public scoreboard asks this often (UPG-403)

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function clockText(s) { s = Math.max(0, Math.floor(s)); return pad(Math.floor(s / 60)) + ':' + pad(s % 60); }
  function tapId() {
    if (window.crypto && window.crypto.randomUUID) { return window.crypto.randomUUID(); }
    return 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function csrf() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }

  function num(v) { return v === '' || v === null || v === undefined ? null : (parseInt(v, 10) || 0); }

  // The raid clock's words (UPG-413): the seconds left, "time over", or how long he took
  function raidText(secs, running, limit, scorer) {
    if (secs === null) { return scorer ? limit + ' s' : ''; }
    if (running && secs < limit) { return scorer ? (limit - secs) + ' s left' : 'Raid · ' + (limit - secs) + ' s'; }
    if (running) { return scorer ? 'Time over · ' + secs + ' s' : 'Raid time over'; }
    return 'Back in ' + secs + ' s';
  }

  // The match clock, the half's time left or the break's (UPG-439) and the raid clock, ticked between updates
  function Clock(root) {
    var raidEl = root.querySelector('[data-raid-clock]');
    var s0 = {
      clock: num(root.getAttribute('data-clock')) || 0,
      running: root.getAttribute('data-running') === 'true',
      half: num(root.getAttribute('data-half-seconds')) || 0,
      phase: root.getAttribute('data-phase'),
      breakLeft: num(root.getAttribute('data-break-left')),
      raid: raidEl && raidEl.getAttribute('data-secs') !== '' ?
        { secs: num(raidEl.getAttribute('data-secs')), running: raidEl.getAttribute('data-running') === 'true' } : null,
      limit: raidEl ? (num(raidEl.getAttribute('data-limit')) || 30) : 30
    };
    var at = Date.now();
    var el = root.querySelector('[data-clock-text]');
    function show() {
      var gone = (Date.now() - at) / 1000;
      var s = Math.floor(s0.clock + (s0.running ? gone : 0));
      if (el) { el.textContent = clockText(s); }
      var left = root.querySelector('[data-clock-left]');
      if (left) {
        if ((s0.phase === 'first_half' || s0.phase === 'second_half') && s0.half) {
          var l = s0.half - s;
          left.hidden = false;
          left.classList.toggle('is-up', l <= 0);
          left.textContent = l > 0 ? clockText(l) + ' left' : 'Time up';
        } else if (s0.phase === 'half_time' && s0.breakLeft !== null) {
          var b = s0.breakLeft - Math.floor(gone);
          left.hidden = false;
          left.classList.remove('is-up');
          left.textContent = b > 0 ? 'Break · ' + clockText(b) + ' left' : 'Break over';
        } else {
          left.hidden = true;
        }
      }
      var r = root.querySelector('[data-raid-clock]');
      if (r) {
        var rc = s0.raid;
        r.hidden = !rc;
        if (rc) {
          var secs = rc.secs + (rc.running ? Math.floor(gone) : 0);
          r.textContent = raidText(secs, rc.running, s0.limit, false);
          r.classList.toggle('is-over', rc.running && secs >= s0.limit);
        }
      }
    }
    setInterval(show, 250);
    show();
    return {
      set: function (state) {
        s0 = { clock: state.clock, running: state.running, half: state.half_seconds || 0, phase: state.phase,
               breakLeft: state.break_left === null || state.break_left === undefined ? null : state.break_left,
               raid: state.raid_clock || null, limit: state.raid_seconds || 30 };
        at = Date.now();
        show();
      }
    };
  }

  // A list of raids, each with how long it took when the raid clock ran (UPG-413)
  function fillList(list, lines, secs) {
    list.innerHTML = '';
    lines.forEach(function (line, i) {
      var li = el('li', '', line);
      if (secs && secs[i]) { li.appendChild(document.createTextNode(' ')); li.appendChild(el('span', 'raid-secs', '· ' + secs[i])); }
      list.appendChild(li);
    });
  }

  function render(root, state, clock) {
    ['home', 'away'].forEach(function (side) {
      var score = root.querySelector('[data-score="' + side + '"]');
      if (score) { score.textContent = state[side].total; }
      var halves = root.querySelector('[data-halves="' + side + '"]');
      if (halves) { halves.textContent = state[side].halves[0] + ' · ' + state[side].halves[1]; }
      ['raid', 'tackle', 'extra'].forEach(function (k) {
        var cell = root.querySelector('[data-split="' + side + '-' + k + '"]');
        if (cell) { cell.textContent = state[side][k]; }
      });
    });
    var phase = root.querySelector('[data-phase-name]');
    if (phase) { phase.textContent = state.phase_name; }
    var dot = root.querySelector('[data-live-dot]');
    if (dot) { dot.hidden = ['first_half', 'half_time', 'second_half', 'tiebreak'].indexOf(state.phase) < 0; }
    // PKL mode: who raids, do-or-die, the mat; and the tie-breaker (UPG-396, UPG-397)
    [['[data-mat-line]', state.mat_text], ['[data-shootout-line]', state.shootout_text],
     ['[data-stop-line]', state.stopped_for]].forEach(function (x) {
      var el = root.querySelector(x[0]);
      if (el) { el.textContent = x[1] || ''; el.hidden = !x[1]; }
    });
    var result = root.querySelector('[data-result-line]');     // who won, at full time (UPG-456)
    if (result) {
      result.hidden = !state.result_text;
      result.querySelector('[data-result-text]').textContent = state.result_text || '';
    }
    var list = root.querySelector('[data-recent]');
    if (list) { fillList(list, state.recent, state.recent_secs); }
    var feed = root.querySelector('[data-feed]');
    if (feed && state.feed) { fillList(feed, state.feed, state.feed_secs); }
    var tossLine = root.querySelector('[data-toss-line]');
    if (tossLine) {
      var showToss = state.toss && state.phase === 'not_started';
      tossLine.hidden = !showToss;
      if (showToss) { tossLine.querySelector('[data-toss-text]').textContent = state.toss.text; }
    }
    var watch = root.querySelector('[data-watch-count]');
    if (watch && state.watching) { watch.textContent = state.watching; }
    var sheet = root.querySelector('[data-sheet-link]');
    if (sheet) {
      sheet.hidden = state.phase === 'not_started';
      var prov = sheet.querySelector('[data-sheet-provisional]');
      if (prov) { prov.hidden = state.phase === 'full_time'; }
    }
    var potm = root.querySelector('[data-potm-line]');
    if (potm) {
      var pm = state.potm;
      potm.hidden = !pm;
      if (pm) {
        potm.querySelector('[data-potm-name]').textContent = pm.tag;
        potm.querySelector('[data-potm-meta]').textContent = '· ' + pm.team_name + ' · ' + pm.points + ' point' + (pm.points === 1 ? '' : 's');
      }
    }
    var host = root.querySelector('[data-mat-boxes-host]');
    if (host) { matBoxes(host, state); }
    var waiting = root.querySelector('[data-waiting]');
    if (waiting) { waiting.hidden = true; }
    root.setAttribute('data-phase', state.phase);
    clock.set(state);
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }

  // Each team's players on the mat and out by jersey number, and who is raiding
  // (UPG-421): the same boxes as includes/live_mat_boxes.html
  function matBoxes(host, state) {
    var mat = state.mat;
    host.innerHTML = '';
    if (!mat || !mat.named || !mat.players) { return; }
    var now = state.raiding_now;
    // Who raids is in the mat line; this line names the raider once he's tapped (UPG-436)
    if (now) {
      var line = el('p', 'mat-now');
      line.setAttribute('data-raiding-line', '');
      line.appendChild(el('span', 'mat-now__label', 'Raiding now'));
      line.appendChild(document.createTextNode(' '));
      line.appendChild(el('b', 'mat-now__no', now.jersey ? '#' + now.jersey : ''));
      line.appendChild(document.createTextNode(' '));
      line.appendChild(el('strong', '', now.name));
      line.appendChild(document.createTextNode(' '));
      line.appendChild(el('span', 'mat-now__team', now.team_name));
      if (mat.do_or_die) {
        line.appendChild(document.createTextNode(' '));
        line.appendChild(el('span', 'mat-now__dod', 'Do-or-die'));
      }
      host.appendChild(line);
    }
    var boxes = el('div', 'mat-boxes');
    ['home', 'away'].forEach(function (side) {
      var p = mat.players[side];
      var box = el('section', 'mat-box' + (mat.raider === side ? ' mat-box--raiding' : ''));
      box.setAttribute('data-mat-box', side);
      box.appendChild(el('h3', 'mat-box__team', state[side].name));
      var label = el('div', 'mat-box__label', 'On the mat · ');
      var count = el('span', '', String(p.on.length));
      count.setAttribute('data-box-count', side);
      label.appendChild(count);
      box.appendChild(label);
      [['on', p.on, 'mat-box__chips'], ['out', p.out, 'mat-box__chips mat-box__chips--out']].forEach(function (g) {
        if (g[0] === 'out') { box.appendChild(el('div', 'mat-box__label mat-box__label--out', 'Out · ' + g[1].length)); }
        var chips = el('div', g[2]);
        chips.setAttribute(g[0] === 'on' ? 'data-box-on' : 'data-box-out', side);
        g[1].forEach(function (x) {
          var raiding = g[0] === 'on' && now && now.team === side && now.name === x.name;
          var chip = el('span', 'mat-chip' + (g[0] === 'out' ? ' mat-chip--out' : '') + (raiding ? ' mat-chip--raiding' : ''));
          chip.setAttribute('data-chip', x.name);
          chip.appendChild(el('b', '', x.jersey || '–'));
          chip.appendChild(el('small', '', x.name));
          chips.appendChild(chip);
        });
        if (g[0] === 'out' && !g[1].length) { chips.appendChild(el('span', 'mat-box__none', 'Nobody out')); }
        box.appendChild(chips);
      });
      // Off for a card (UPG-447): a yellow card's time left, or a red card
      var carded = p.carded || [];
      if (carded.length) {
        box.appendChild(el('div', 'mat-box__label mat-box__label--card', 'Off · card · ' + carded.length));
        var cc = el('div', 'mat-box__chips mat-box__chips--card');
        cc.setAttribute('data-box-card', side);
        carded.forEach(function (x) {
          var chip = el('span', 'mat-chip mat-chip--card mat-chip--' + x.card);
          chip.setAttribute('data-chip', x.name);
          chip.appendChild(el('b', '', x.jersey || '–'));
          chip.appendChild(el('small', '', x.name));
          chip.appendChild(el('em', 'mat-chip__left', x.left === null || x.left === undefined ? 'Red card' : clockText(x.left) + ' left'));
          cc.appendChild(chip);
        });
        box.appendChild(cc);
      }
      boxes.appendChild(box);
    });
    host.appendChild(boxes);
  }

  // Which buttons make sense in each phase
  var ALLOWED = {
    not_started: ['start'],
    first_half: ['pause', 'resume', 'half_time'],
    half_time: ['second_half'],
    second_half: ['pause', 'resume', 'full_time'],
    tiebreak: ['full_time', 'back'],
    full_time: []
  };

  function scorer(root) {
    var url = root.getAttribute('data-url');
    var clock = Clock(root);
    var message = root.querySelector('[data-message]');
    var queue = [];
    var busy = false;

    function refreshButtons() {
      var phase = root.getAttribute('data-phase');
      var scoring = phase === 'first_half' || phase === 'second_half';
      root.querySelectorAll('[data-point]').forEach(function (b) { b.disabled = !scoring; });
      root.querySelectorAll('[data-undo]').forEach(function (undo) {   // below, and up top in full screen (UPG-470)
        undo.disabled = phase === 'full_time' || phase === 'not_started';
      });
      root.setAttribute('data-busy', queue.length ? 'true' : 'false');
      var reopen = root.querySelector('[data-reopen]');
      if (reopen) { reopen.hidden = phase !== 'full_time'; }
      root.querySelectorAll('[data-remove]').forEach(function (b) { b.disabled = phase === 'full_time'; });
      root.querySelectorAll('[data-phase-action]').forEach(function (b) {
        b.hidden = (ALLOWED[phase] || []).indexOf(b.getAttribute('data-phase-action')) < 0;
      });
    }

    function say(text, bad) {
      if (!message) { return; }
      message.textContent = text || '';
      message.className = 'live-message' + (bad ? ' live-message--bad' : '');
    }

    function renderEntries(entries) {
      var list = root.querySelector('[data-entries]');
      if (!list || !entries) { return; }
      list.innerHTML = '';
      entries.forEach(function (e) {
        var li = document.createElement('li');
        var text = document.createElement('span');
        text.textContent = e.text + ' · ' + (e.half === 1 ? 'H1' : 'H2');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-sm btn-outline-danger';
        btn.setAttribute('data-remove', e.id);
        btn.textContent = 'Remove';
        li.appendChild(text);
        li.appendChild(document.createTextNode(' '));
        li.appendChild(btn);
        list.appendChild(li);
      });
      var summary = root.querySelector('[data-all-points] summary');
      if (summary) { summary.textContent = 'All points (' + entries.length + '): remove a wrong one'; }
    }

    function next() {
      if (busy || !queue.length) { return; }
      busy = true;
      var body = queue[0];
      fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify(body)
      }).then(function (resp) {
        return resp.json().then(function (data) { return { status: resp.status, data: data }; });
      }).then(function (r) {
        queue.shift();
        busy = false;
        if (r.data && r.data.ok) {
          // While more taps wait, keep their scores shown; the last answer has them all
          if (!queue.length) {
            render(root, r.data.state, clock);
            renderEntries(r.data.entries);
            renderPanel(r.data.panel);
          }
          if (body.op !== 'state') {
            var st = r.data.state || {};
            var first = st.recent && st.recent[0];
            var saved = (body.op === 'raid' || body.op === 'call') && first ? 'Saved: ' + first + (st.recent_secs && st.recent_secs[0] ? ' · ' + st.recent_secs[0] : '') :
              body.op === 'toss' && st.toss ? 'Saved: ' + st.toss.text + '.' :
              body.op === 'timings' ? 'Saved: ' + st.half_minutes + '-minute halves, a ' + st.break_minutes + '-minute break.' : '';
            say(queue.length ? 'Sending…' : saved);
          }
        } else {
          say((r.data && r.data.error) || 'That didn\'t save.', true);
          if (body.op !== 'state') { resync(); }
        }
        refreshButtons();
        next();
      }).catch(function () {
        // Offline or a dropped connection: the same tap (same id) is tried again
        busy = false;
        say('No connection. Retrying…', true);
        setTimeout(next, 2000);
      });
    }

    function renderPanel(html) {
      var panel = root.querySelector('[data-panel]');
      if (panel && typeof html === 'string') { panel.innerHTML = html; rcAt = Date.now(); }
      bonusApply();
      reapply();
      raidTick();
    }

    // The raid clock (UPG-413): a stopwatch, Space or its button; ticked here between taps
    var rcAt = Date.now();
    var buzzed = false;
    function raidBox() { return root.querySelector('[data-raid-clock-box]'); }
    function raidNow(box) {
      var s = box.getAttribute('data-secs');
      if (s === '' || s === null) { return null; }
      var running = box.getAttribute('data-running') === 'true';
      return { secs: (parseInt(s, 10) || 0) + (running ? Math.floor((Date.now() - rcAt) / 1000) : 0), running: running };
    }
    function raidTick() {
      var box = raidBox();
      if (!box) { return; }
      var limit = parseInt(box.getAttribute('data-limit'), 10) || 30;
      var rc = raidNow(box);
      var running = !!(rc && rc.running);
      box.querySelector('[data-raid-clock-text]').textContent = raidText(rc ? rc.secs : null, running, limit, true);
      var over = running && rc.secs >= limit;
      box.classList.toggle('is-over', over);
      box.classList.toggle('is-running', running);
      var btn = box.querySelector('[data-raid-clock-btn]');
      if (btn && btn.firstChild) { btn.firstChild.textContent = running ? 'Stop: raider back ' : 'Start: raider goes '; }
      if (!over) { buzzed = false; return; }
      if (!buzzed) {
        buzzed = true;
        if (navigator.vibrate) { navigator.vibrate([200, 100, 200]); }
        say('Raid time over (' + limit + ' s). If the raider isn\'t back, tap Raid time over.', true);
      }
    }
    setInterval(raidTick, 250);
    function raidToggle() {
      var box = raidBox();
      if (!box) { return false; }
      var rc = raidNow(box);
      if (rc && rc.running) {
        box.setAttribute('data-secs', String(rc.secs));
        box.setAttribute('data-running', 'false');
        send({ op: 'raid_clock', action: 'stop' });
      } else {
        box.setAttribute('data-secs', '0');
        box.setAttribute('data-running', 'true');
        send({ op: 'raid_clock', action: 'start' });
      }
      rcAt = Date.now();
      raidTick();
      return true;
    }
    function typing(t) {
      if (!t || !t.tagName) { return false; }
      if (t.isContentEditable || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT') { return true; }
      return t.tagName === 'INPUT' && !/^(checkbox|radio|button|submit)$/i.test(t.type || '');
    }
    function isSpace(e) { return e.key === ' ' || e.code === 'Space' || e.key === 'Spacebar'; }
    // Space starts and stops the raid clock; it never presses the button that has the focus
    document.addEventListener('keydown', function (e) {
      if (!isSpace(e) || typing(e.target) || !raidBox()) { return; }
      e.preventDefault();
      if (!e.repeat) { raidToggle(); }
    });
    document.addEventListener('keyup', function (e) {
      if (isSpace(e) && !typing(e.target) && raidBox()) { e.preventDefault(); }
    });

    // Full screen scoring (UPG-470): the score, the clock and the match's buttons
    // stay at the top, the rest of the site goes; kept on this device until turned off
    var FOCUS_KEY = 'saptha.scorerFocus';
    function focusSet(on, fromTap) {
      root.classList.toggle('is-focus', on);
      document.documentElement.classList.toggle('live-focus-on', on);
      var btn = root.querySelector('[data-focus-toggle]');
      if (btn) {
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        var label = btn.querySelector('[data-focus-label]');
        if (label) { label.textContent = on ? 'Exit full screen' : 'Full screen scoring'; }
        var icon = btn.querySelector('i');
        if (icon) { icon.className = 'fas ' + (on ? 'fa-compress' : 'fa-expand'); }
      }
      try { if (on) { window.localStorage.setItem(FOCUS_KEY, '1'); } else { window.localStorage.removeItem(FOCUS_KEY); } } catch (err) { /* private mode */ }
      if (!fromTap) { return; }
      var d = document;
      if (on && d.documentElement.requestFullscreen && !d.fullscreenElement) {
        d.documentElement.requestFullscreen().catch(function () {});
      } else if (!on && d.fullscreenElement && d.exitFullscreen) {
        d.exitFullscreen().catch(function () {});
      }
    }
    try { if (window.localStorage.getItem(FOCUS_KEY)) { focusSet(true, false); } } catch (err) { /* private mode */ }

    // The bonus as buttons (UPG-465): '' | 'given' | 'missed', kept across a redraw until the raid is saved
    var bonus = '';
    function bonusApply() {
      root.querySelectorAll('[data-bonus-toggle]').forEach(function (b) {
        if (b.disabled) { return; }
        var on = bonus === b.getAttribute('data-bonus-toggle');
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      if (bonus && !root.querySelector('[data-bonus-toggle]:not([disabled])')) { bonus = ''; }
    }

    // The players tapped so far (UPG-420): kept across a redraw of the panel
    var pick = { defenders: [], mode: '', side: '', off: '' };
    function clearPick() { pick = { defenders: [], mode: '', side: '', off: '' }; reapply(); }
    function namedPanel() {
      var panel = root.querySelector('[data-pkl-panel]');
      return panel && panel.getAttribute('data-named') === 'true' ? panel : null;
    }
    function reapply() {
      var panel = namedPanel();
      if (!panel) { return; }
      var still = [];
      panel.querySelectorAll('[data-mat-player][data-role="defender"]').forEach(function (b) {
        var on = pick.defenders.indexOf(b.getAttribute('data-name')) >= 0;
        b.classList.toggle('is-picked', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        if (on) { still.push(b.getAttribute('data-name')); }
      });
      pick.defenders = still;
      panel.querySelectorAll('[data-mat-player]').forEach(function (b) {
        b.classList.toggle('is-off', pick.mode === 'sub' && pick.side === b.getAttribute('data-side') &&
                           pick.off === b.getAttribute('data-name'));
      });
      panel.querySelectorAll('[data-tool]').forEach(function (b) {
        b.classList.toggle('active', pick.mode === b.getAttribute('data-tool') && pick.side === b.getAttribute('data-side'));
      });
      var n = pick.defenders.length;
      panel.querySelectorAll('[data-touch-button]').forEach(function (touch) {   // under the team and below (UPG-466)
        touch.disabled = !n;
        touch.textContent = n ? n + ' touch' + (n === 1 ? '' : 'es') + ' +' + n : 'Touch points: tap the defenders';
        var hint = el('small', 'pkl-hint', n ? 'he touched ' + n + ', they go out' : 'tap who he touched first');
        touch.appendChild(hint);
      });
      guide(panel);
    }
    // The step box over the players (UPG-432): which step, what to tap, what's tapped so far
    function guide(panel) {
      var box = panel.querySelector('[data-guide]');
      if (!box) { return; }
      var raider = panel.querySelector('[data-mat-player][data-role="raider"].is-picked');
      var defs = Array.prototype.map.call(
        panel.querySelectorAll('[data-mat-player][data-role="defender"].is-picked'), nameOf);
      var step = box.querySelector('[data-guide-step]');
      var text = box.querySelector('[data-guide-text]');
      var sum = box.querySelector('[data-raid-summary]');
      var att = box.getAttribute('data-raiding-team'), def = box.getAttribute('data-defending-team');
      text.innerHTML = '';
      if (pick.mode) {
        step.textContent = 'Other';
        text.textContent = MODE_TEXT[pick.mode] + ' Tap the same button again to cancel.';
      } else if (!raider) {
        step.textContent = 'Step 1 of 3';
        text.appendChild(document.createTextNode('Who is raiding? Tap the '));
        text.appendChild(el('strong', '', att));
        text.appendChild(document.createTextNode(' player who goes in (blue side).'));
      } else if (!defs.length) {
        step.textContent = 'Step 2 of 3';
        text.appendChild(document.createTextNode('Did '));
        text.appendChild(el('strong', '', nameOf(raider)));
        text.appendChild(document.createTextNode(' touch anyone? Tap each '));
        text.appendChild(el('strong', '', def));
        text.appendChild(document.createTextNode(' player he touched, or the one who tackled him. Nobody? Tap Empty raid under the raiding team.'));
      } else {
        step.textContent = 'Step 3 of 3';
        text.appendChild(document.createTextNode('Now tap how the raid ended, under the teams: Touch points (' + defs.length +
          ') or Tackled. Tap a defender again to take him off.'));
      }
      sum.innerHTML = '';
      sum.appendChild(document.createTextNode('This raid: '));
      if (!raider) { sum.appendChild(document.createTextNode('no raider yet')); return; }
      sum.appendChild(el('strong', '', nameOf(raider)));
      sum.appendChild(document.createTextNode(defs.length ? ' · touched or tackled by ' : ' raiding'));
      if (defs.length) { sum.appendChild(el('strong', '', defs.join(', '))); }
    }
    function nameOf(b) {
      var no = b.querySelector('.pkl-player__no');
      return (no ? no.textContent + ' ' : '') + b.getAttribute('data-name');
    }
    var MODE_TEXT = {
      sub: 'Substitution: tap the player going off, then the substitute coming on.',
      out_of_bounds: 'Out of bounds: tap the player who stepped out.',
      mat_off: '−1 on the mat: tap the player who goes off.',
      lobby: 'Lobby: tap the player who went into the lobby before a struggle.',
      injury: 'Injury break: tap the injured player. The clock stops; no time-out is used.',
      card_green: 'Green card (a warning): tap the player.',
      card_yellow: 'Yellow card (off for 2 minutes of play): tap the player.',
      card_red: 'Red card (off for the match): tap the player.'
    };

    // A refused tap: show the match as the server has it
    function resync() {
      queue.push({ op: 'state', tap: tapId() });
      next();
    }

    // The score goes up at once; the server's answer confirms it (UPG-403)
    function bump(side, points) {
      var el = root.querySelector('[data-score="' + side + '"]');
      var n = parseInt(points, 10);
      if (el && n > 0) { el.textContent = (parseInt(el.textContent, 10) || 0) + n; }
    }

    function value(sel) {
      var el = root.querySelector(sel);
      return el ? el.value : '';
    }
    function checked(sel) {
      var el = root.querySelector(sel);
      return !!(el && el.checked);
    }

    function send(body) {
      body.tap = tapId();
      queue.push(body);
      say('Sending…');
      next();
    }

    root.addEventListener('click', function (e) {
      if (e.target.closest('[data-raid-clock-btn]')) { raidToggle(); return; }
      if (e.target.closest('[data-focus-toggle]')) { focusSet(!root.classList.contains('is-focus'), true); return; }
      var sw = e.target.closest('[data-raid-clock-switch]');             // the raid clock on or off (UPG-464)
      if (sw) { send({ op: 'raid_clock', action: sw.getAttribute('data-raid-clock-switch') }); return; }
      var bt = e.target.closest('[data-bonus-toggle]');                  // the bonus buttons (UPG-465)
      if (bt) {
        var bk = bt.getAttribute('data-bonus-toggle');
        bonus = bonus === bk ? '' : bk;
        bonusApply();
        say(bonus === 'given' ? 'Bonus +1 goes with this raid.' : bonus === 'missed' ? 'Bonus tried, not given: goes with this raid.' : '');
        return;
      }
      // The toss (UPG-438): the winner and their choice, then Save
      var tossBtn = e.target.closest('[data-toss-pick], [data-toss-choice]');
      if (tossBtn) {
        var attr = tossBtn.hasAttribute('data-toss-pick') ? 'data-toss-pick' : 'data-toss-choice';
        root.querySelectorAll('[' + attr + ']').forEach(function (b) {
          b.classList.toggle('active', b === tossBtn);
          b.setAttribute('aria-pressed', b === tossBtn ? 'true' : 'false');
        });
        return;
      }
      if (e.target.closest('[data-toss-save]')) {
        var won = root.querySelector('[data-toss-pick].active'), chose = root.querySelector('[data-toss-choice].active');
        if (!won || !chose) { say('Tap the team that won the toss and what they chose.', true); return; }
        send({ op: 'toss', winner: won.getAttribute('data-toss-pick'), choice: chose.getAttribute('data-toss-choice') });
        return;
      }
      // The half's and the break's minutes (UPG-439)
      if (e.target.closest('[data-timings-save]')) {
        send({ op: 'timings', half_minutes: value('[data-half-minutes]'), break_minutes: value('[data-break-minutes]') });
        return;
      }
      var point = e.target.closest('[data-point]');
      if (point) {
        var team = point.getAttribute('data-team');
        var player = root.querySelector('[data-player="' + team + '"]');
        send({ op: 'point', team: team, kind: point.getAttribute('data-kind'),
               points: point.getAttribute('data-points') || '', player: player ? player.value : '' });
        bump(team, point.getAttribute('data-add'));
        if (player) { player.value = ''; }
        return;
      }
      // Another player of the match, after full time (UPG-422)
      var potm = e.target.closest('[data-potm-pick]');
      if (potm) {
        if (!window.confirm('Make ' + potm.textContent.trim() + ' the player of the match?')) { return; }
        send({ op: 'potm', team: potm.getAttribute('data-side'), name: potm.getAttribute('data-name') });
        return;
      }
      // Each team's seven before the start (UPG-417)
      var lp = e.target.closest('[data-lineup-pick]');
      if (lp) {
        var lside = lp.getAttribute('data-side');
        var count = root.querySelectorAll('[data-lineup-pick][data-side="' + lside + '"].is-picked').length;
        if (!lp.classList.contains('is-picked') && count >= 7) { say('Seven a team: tap a picked player to take him out first.', true); return; }
        lp.classList.toggle('is-picked');
        lp.setAttribute('aria-pressed', lp.classList.contains('is-picked') ? 'true' : 'false');
        var shown = root.querySelector('[data-lineup-count="' + lside + '"]');
        if (shown) { shown.textContent = root.querySelectorAll('[data-lineup-pick][data-side="' + lside + '"].is-picked').length; }
        say('');
        return;
      }
      if (e.target.closest('[data-lineup-save]')) {
        var sides = {};
        ['home', 'away'].forEach(function (sd) {
          sides[sd] = Array.prototype.map.call(
            root.querySelectorAll('[data-lineup-pick][data-side="' + sd + '"].is-picked'),
            function (b) { return b.getAttribute('data-name'); });
        });
        if (sides.home.length !== 7 || sides.away.length !== 7) {
          say('Pick 7 players for each team (now ' + sides.home.length + ' and ' + sides.away.length + ').', true);
          return;
        }
        send({ op: 'lineup', home: sides.home, away: sides.away });
        return;
      }
      // The players by jersey number (UPG-420): a mode, a player, a substitute
      var mode = e.target.closest('[data-tool]');
      if (mode) {
        var m = mode.getAttribute('data-tool'), ms = mode.getAttribute('data-side');
        if (pick.mode === m && pick.side === ms) { clearPick(); say(''); return; }
        pick.mode = m; pick.side = ms; pick.off = '';
        reapply();
        say(MODE_TEXT[m] || '');
        return;
      }
      var pl = e.target.closest('[data-mat-player]');
      if (pl) {
        var side = pl.getAttribute('data-side'), who = pl.getAttribute('data-name'), role = pl.getAttribute('data-role');
        if (pick.mode && pick.side === side) {
          if (pick.mode === 'sub') { pick.off = who; reapply(); say('Now tap the substitute coming on for ' + nameOf(pl) + '.'); return; }
          // Cards (UPG-447) and an injury break (UPG-449): any of the seven, out ones too
          if (pick.mode.indexOf('card_') === 0) {
            var card = pick.mode.slice(5);
            if (role === 'carded' && !(card === 'red' && pl.getAttribute('data-card') === 'yellow')) {
              say(nameOf(pl) + ' is off for a card already.', true); return;
            }
            if (!window.confirm(card.charAt(0).toUpperCase() + card.slice(1) + ' card for ' + nameOf(pl) + '?')) { return; }
            send({ op: 'call', kind: 'card', card: card, team: side, player: who });
            clearPick();
            return;
          }
          if (pick.mode === 'injury') {
            send({ op: 'call', kind: 'stoppage', reason: 'injury', team: side, player: who });
            clearPick();
            return;
          }
          if (role === 'out' || role === 'carded') { say(nameOf(pl) + ' is out already.', true); return; }
          if (pick.mode === 'lobby') { send({ op: 'call', kind: 'out_of_bounds', where: 'lobby', team: side, player: who }); }
          if (pick.mode === 'out_of_bounds') { send({ op: 'call', kind: 'out_of_bounds', team: side, player: who }); }
          if (pick.mode === 'mat_off') { send({ op: 'call', kind: 'mat', team: side, change: -1, player: who }); }
          clearPick();
          return;
        }
        if (role === 'raider') {
          if (pl.classList.contains('is-picked')) { say(nameOf(pl) + ' is the raider. To change, tap another player.'); return; }
          root.querySelectorAll('[data-mat-player][data-role="raider"]').forEach(function (b) { b.classList.remove('is-picked'); });
          pl.classList.add('is-picked');
          reapply();
          var rbox = raidBox();                           // his 30 seconds start (UPG-413)
          if (rbox && !(raidNow(rbox) || {}).running) {
            rbox.setAttribute('data-secs', '0');
            rbox.setAttribute('data-running', 'true');
            rcAt = Date.now();
            raidTick();
          }
          send({ op: 'raider', name: who });
          return;
        }
        if (role === 'carded') {
          say(nameOf(pl) + ' is off for a card. A yellow card comes back after 2 minutes of play; a red card is off for the match.', true);
          return;
        }
        if (role === 'out') {
          say(nameOf(pl) + ' is out. Players come back in this order when their team scores; or use +1 on the mat under Calls.', true);
          return;
        }
        if (role === 'defender') {
          var i = pick.defenders.indexOf(who);
          if (i >= 0) { pick.defenders.splice(i, 1); } else { pick.defenders.push(who); }
          reapply();
        }
        return;
      }
      var bench = e.target.closest('[data-bench]');
      if (bench) {
        var bs = bench.getAttribute('data-side');
        if (pick.mode !== 'sub' || pick.side !== bs || !pick.off) {
          say('Tap Substitution, then the player going off, then this substitute.', true);
          return;
        }
        var offBtn = root.querySelector('[data-mat-player][data-side="' + bs + '"][data-name="' + pick.off.replace(/"/g, '\\"') + '"]');
        if (!window.confirm('Bring on ' + nameOf(bench) + ' for ' + (offBtn ? nameOf(offBtn) : pick.off) + '?')) { return; }
        send({ op: 'call', kind: 'sub', team: bs, off: pick.off, on: bench.getAttribute('data-name') });
        clearPick();
        return;
      }
      // PKL mode: one raid as it ended, or a referee's call (UPG-397)
      var raid = e.target.closest('[data-raid]');
      if (raid) {
        var panel = root.querySelector('[data-pkl-panel]');
        var body = { op: 'raid', team: panel ? panel.getAttribute('data-raider') : '',
                     outcome: raid.getAttribute('data-outcome'), touches: raid.getAttribute('data-touches') || '',
                     bonus: bonus === 'given', raider: value('[data-pkl-raider]'),
                     tackler: value('[data-pkl-tackler]'), bonus_missed: bonus === 'missed' };
        if (namedPanel()) {
          var picked = root.querySelector('[data-mat-player][data-role="raider"].is-picked');
          body.raider = picked ? picked.getAttribute('data-name') : (panel.getAttribute('data-raiding-now') || '');
          if (!body.raider) { say('Tap the raider first (step 1).', true); return; }
          if (body.outcome === 'tackled' && !pick.defenders.length &&
              !window.confirm('Nobody is tapped as the tackler. Save the tackle without his name?')) { return; }
          body.touched = pick.defenders.slice();
          body.touches = body.touched.length || '';
          body.tackler = body.outcome === 'tackled' ? (pick.defenders[0] || '') : '';
        }
        send(body);
        bonus = '';
        clearPick();
        bonusApply();
        return;
      }
      var call = e.target.closest('[data-call]');
      if (call) {
        var kind = call.getAttribute('data-kind');
        var cteam = call.getAttribute('data-team') || '';
        if (kind === 'turn' && !window.confirm('Give the next raid to the other team?')) { return; }
        var cbody = { op: 'call', kind: kind, team: cteam,
                      upheld: call.getAttribute('data-upheld') === '1', change: call.getAttribute('data-change') || 0,
                      reason: call.getAttribute('data-reason') || '',
                      where: call.getAttribute('data-where') || '' };
        if (kind === 'card') {                          // without line-ups: the card by its button (UPG-447)
          cbody.card = call.getAttribute('data-card');
          cbody.player = value('[data-card-player="' + cteam + '"]');
          if (!window.confirm(call.textContent.trim() + (cbody.player ? ' for ' + cbody.player : '') + '?')) { return; }
        }
        send(cbody);
        return;
      }
      // The tie-breaker (UPG-396)
      var shoot = e.target.closest('[data-shootout]');
      if (shoot) {
        send({ op: 'shootout', team: value('[data-sh-team]'), outcome: shoot.getAttribute('data-outcome'),
               touches: shoot.getAttribute('data-touches') || '', bonus: checked('[data-sh-bonus]') });
        return;
      }
      var decide = e.target.closest('[data-decide]');
      if (decide) {
        if (!window.confirm(decide.textContent.trim() + '?')) { return; }
        send({ op: 'decide', way: decide.getAttribute('data-way'), winner: decide.getAttribute('data-winner') });
        return;
      }
      if (e.target.closest('[data-undo]')) {
        send({ op: 'undo' });
        return;
      }
      var remove = e.target.closest('[data-remove]');
      if (remove) {
        if (!window.confirm('Remove this point?')) { return; }
        send({ op: 'remove', entry: remove.getAttribute('data-remove') });
        return;
      }
      if (e.target.closest('[data-reopen]')) {
        if (!window.confirm('Take the result off the fixtures and go back to the 2nd half?')) { return; }
        send({ op: 'reopen' });
        return;
      }
      var phase = e.target.closest('[data-phase-action]');
      if (phase) {
        var action = phase.getAttribute('data-phase-action');
        var winner = root.querySelector('[data-winner]');
        if (action === 'full_time') {
          var h = root.querySelector('[data-score="home"]').textContent;
          var a = root.querySelector('[data-score="away"]').textContent;
          var ask = 'End the match and save ' + h + ' – ' + a + ' as the result?';
          if (root.getAttribute('data-phase') === 'second_half' && h === a && root.getAttribute('data-tiebreak') === 'true') {
            ask = 'It\'s level at ' + h + ' – ' + a + '. Start the tie-breaker (5 raids each)?';
          }
          if (!window.confirm(ask)) { return; }
        }
        send({ op: 'phase', action: action, winner: winner ? winner.value : '', first: value('[data-first]') });
      }
    });
    reapply();
    refreshButtons();
  }

  // The toss, played once on each screen (UPG-438): a coin, the winner's logo
  // and "won the toss", then what they chose
  var TOSS_FRESH = 600;      // seconds after the toss that a page opening still plays it
  function initials(name) {
    return String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }
  function badge(logo, name, cls) {
    if (logo) { var img = el('img', cls); img.src = logo; img.alt = ''; return img; }
    return el('span', cls + ' toss-show__initials', initials(name));
  }
  function playToss(toss, logos, names) {
    var show = el('div', 'toss-show');
    show.setAttribute('data-toss-show', '');
    show.setAttribute('role', 'status');
    var card = el('div', 'toss-show__card');
    var coin = el('div', 'toss-show__coin');
    coin.appendChild(badge(logos.home, names.home, 'toss-show__face toss-show__face--front'));
    coin.appendChild(badge(logos.away, names.away, 'toss-show__face toss-show__face--back'));
    card.appendChild(el('div', 'toss-show__eyebrow', 'The toss'));
    card.appendChild(coin);
    var won = el('div', 'toss-show__won');
    won.appendChild(badge(logos[toss.winner], toss.team_name, 'toss-show__logo'));
    won.appendChild(el('strong', 'toss-show__team', toss.team_name));
    won.appendChild(el('span', 'toss-show__line', 'won the toss'));
    card.appendChild(won);
    card.appendChild(el('div', 'toss-show__chose', 'and ' + toss.chose));
    show.appendChild(card);
    document.body.appendChild(show);
    function close() { if (show.parentNode) { show.parentNode.removeChild(show); } }
    show.addEventListener('click', close);
    show.classList.add('is-flip');
    setTimeout(function () { show.classList.add('is-won'); }, 1800);
    setTimeout(function () { show.classList.add('is-chose'); }, 4300);
    setTimeout(close, 8000);
  }
  function tossOnce(root, state) {
    var toss = state && state.toss;
    if (!toss || !toss.at || state.phase === 'full_time') { return; }
    if (typeof toss.age === 'number' && toss.age > TOSS_FRESH) { return; }
    var key = 'sv-toss:' + root.getAttribute('data-url') + ':' + toss.at;
    try {
      if (window.localStorage.getItem(key)) { return; }
      window.localStorage.setItem(key, '1');
    } catch (e) { /* private mode: play it anyway */ }
    playToss(toss, { home: root.getAttribute('data-logo-home') || '', away: root.getAttribute('data-logo-away') || '' },
             { home: state.home.name, away: state.away.name });
  }

  function board(root) {
    var url = root.getAttribute('data-url');
    var clock = Clock(root);
    // Keep a screen showing the match awake where the browser allows it
    var lock = null;
    function wake() {
      if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') { return; }
      navigator.wakeLock.request('screen').then(function (l) { lock = l; }).catch(function () {});
    }
    document.addEventListener('visibilitychange', function () { if (!lock || lock.released) { wake(); } });
    wake();
    function poll() {
      fetch(url, { credentials: 'same-origin' }).then(function (resp) {
        return resp.ok ? resp.json() : null;
      }).then(function (data) {
        if (data && data.ok) { render(root, data.state, clock); tossOnce(root, data.state); }
        // After full time it still looks now and then: a match reopened by mistake goes on
        setTimeout(poll, data && data.ok && data.state.phase === 'full_time' ? POLL_MS * 10 : POLL_MS);
      }).catch(function () { setTimeout(poll, POLL_MS * 2); });
    }
    setTimeout(poll, root.getAttribute('data-phase') === 'full_time' ? POLL_MS * 10 : POLL_MS);
  }

  document.querySelectorAll('[data-live-scorer]').forEach(scorer);
  document.querySelectorAll('[data-live-board]').forEach(board);
})();
