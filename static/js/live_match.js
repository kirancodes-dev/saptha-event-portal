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

  var POLL_MS = 3000;

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function clockText(s) { s = Math.max(0, Math.floor(s)); return pad(Math.floor(s / 60)) + ':' + pad(s % 60); }
  function tapId() {
    if (window.crypto && window.crypto.randomUUID) { return window.crypto.randomUUID(); }
    return 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function csrf() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }

  function Clock(root) {
    var base = parseInt(root.getAttribute('data-clock') || '0', 10) || 0;
    var running = root.getAttribute('data-running') === 'true';
    var at = Date.now();
    var el = root.querySelector('[data-clock-text]');
    function show() {
      if (!el) { return; }
      var s = base + (running ? (Date.now() - at) / 1000 : 0);
      el.textContent = clockText(s);
    }
    setInterval(show, 1000);
    return {
      set: function (seconds, isRunning) { base = seconds; running = isRunning; at = Date.now(); show(); }
    };
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
    if (dot) { dot.hidden = ['first_half', 'half_time', 'second_half'].indexOf(state.phase) < 0; }
    var list = root.querySelector('[data-recent]');
    if (list) {
      list.innerHTML = '';
      state.recent.forEach(function (line) {
        var li = document.createElement('li');
        li.textContent = line;
        list.appendChild(li);
      });
    }
    var waiting = root.querySelector('[data-waiting]');
    if (waiting) { waiting.hidden = true; }
    root.setAttribute('data-phase', state.phase);
    clock.set(state.clock, state.running);
  }

  // Which buttons make sense in each phase
  var ALLOWED = {
    not_started: ['start'],
    first_half: ['pause', 'resume', 'half_time'],
    half_time: ['second_half'],
    second_half: ['pause', 'resume', 'full_time'],
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
      var undo = root.querySelector('[data-undo]');
      if (undo) { undo.disabled = phase === 'full_time' || phase === 'not_started'; }
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
          render(root, r.data.state, clock);
          renderEntries(r.data.entries);
          say(queue.length ? 'Sending…' : '');
        } else {
          say((r.data && r.data.error) || 'That didn\'t save.', true);
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

    function send(body) {
      body.tap = tapId();
      queue.push(body);
      say('Sending…');
      next();
    }

    root.addEventListener('click', function (e) {
      var point = e.target.closest('[data-point]');
      if (point) {
        var team = point.getAttribute('data-team');
        var player = root.querySelector('[data-player="' + team + '"]');
        send({ op: 'point', team: team, kind: point.getAttribute('data-kind'),
               points: point.getAttribute('data-points') || '', player: player ? player.value : '' });
        if (player) { player.value = ''; }
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
          if (!window.confirm('End the match and save ' + h + ' – ' + a + ' as the result?')) { return; }
        }
        send({ op: 'phase', action: action, winner: winner ? winner.value : '' });
      }
    });
    refreshButtons();
  }

  function board(root) {
    var url = root.getAttribute('data-url');
    var clock = Clock(root);
    function poll() {
      fetch(url, { credentials: 'same-origin' }).then(function (resp) {
        return resp.ok ? resp.json() : null;
      }).then(function (data) {
        if (data && data.ok) { render(root, data.state, clock); }
        // After full time it still looks now and then: a match reopened by mistake goes on
        setTimeout(poll, data && data.ok && data.state.phase === 'full_time' ? POLL_MS * 10 : POLL_MS);
      }).catch(function () { setTimeout(poll, POLL_MS * 2); });
    }
    setTimeout(poll, root.getAttribute('data-phase') === 'full_time' ? POLL_MS * 10 : POLL_MS);
  }

  document.querySelectorAll('[data-live-scorer]').forEach(scorer);
  document.querySelectorAll('[data-live-board]').forEach(board);
})();
