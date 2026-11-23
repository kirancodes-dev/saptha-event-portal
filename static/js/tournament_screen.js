/* The big screen (UPG-392): asks for its contents every few seconds, ticks
 * the match clocks in between, shows the time of day, goes full screen on a
 * click and keeps the display awake where the browser allows it. */
(function () {
  'use strict';

  var POLL_MS = 2000;   // UPG-403: the server renders it once for every screen and phone, and says when it's unchanged
  var root = document.querySelector('[data-screen]');
  if (!root) { return; }
  var url = root.getAttribute('data-url');
  var offline = document.querySelector('[data-screen-offline]');
  var shownAt = Date.now();
  var last = root.innerHTML;
  var etag = '';

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function tick() {
    var gone = (Date.now() - shownAt) / 1000;
    root.querySelectorAll('[data-screen-clock]').forEach(function (el) {
      var s = parseInt(el.getAttribute('data-screen-clock'), 10) || 0;
      if (el.getAttribute('data-running') === 'true') { s += gone; }
      s = Math.max(0, Math.floor(s));
      el.textContent = pad(Math.floor(s / 60)) + ':' + pad(s % 60);
    });
    // The half's or the break's time left (UPG-439)
    root.querySelectorAll('[data-screen-left]').forEach(function (el) {
      var left = parseInt(el.getAttribute('data-screen-left'), 10) || 0;
      if (el.getAttribute('data-running') === 'true') { left -= gone; }
      left = Math.max(0, Math.ceil(left));
      var prefix = el.getAttribute('data-prefix') || '';
      el.textContent = !prefix && left === 0 ? 'Time up' : prefix + pad(Math.floor(left / 60)) + ':' + pad(left % 60) + ' left';
      el.classList.toggle('is-up', !prefix && left === 0);
    });
    // The raid clock (UPG-413): 30 seconds counting down while the raider is out
    root.querySelectorAll('[data-screen-raid]').forEach(function (el) {
      var secs = parseFloat(el.getAttribute('data-screen-raid')) || 0;
      var limit = parseInt(el.getAttribute('data-limit'), 10) || 30;
      var running = el.getAttribute('data-running') === 'true';
      if (running) { secs += gone; }
      var whole = Math.floor(secs);
      el.textContent = !running ? 'Back in ' + whole + ' s' : whole >= limit ? 'Raid time over' : 'Raid · ' + (limit - whole) + ' s';
      el.classList.toggle('is-over', running && whole >= limit);
    });
    var now = document.querySelector('[data-screen-now]');
    if (now) {
      var d = new Date();
      now.textContent = pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
  }

  // While a match is live, how many watch it, in the QR code's place (UPG-435)
  var slot = document.querySelector('[data-screen-watch-slot]');
  var qr = document.querySelector('[data-screen-qr]');
  function watching() {
    var src = root.querySelector('template[data-screen-watch]');
    if (slot) {
      if (src) { slot.replaceChildren(src.content.cloneNode(true)); } else { slot.replaceChildren(); }
      slot.hidden = !src;
    }
    if (qr) { qr.hidden = !!src; }
  }

  // A toss just made (UPG-438), played once on this screen: a coin, the
  // winner's logo and "won the toss", then what they chose
  function badge(logo, name, cls) {
    var b;
    if (logo) { b = document.createElement('img'); b.src = logo; b.alt = ''; } else {
      b = document.createElement('span');
      b.textContent = String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
      cls += ' toss-show__initials';
    }
    b.className = cls;
    return b;
  }
  function part(tag, cls, text) {
    var x = document.createElement(tag);
    x.className = cls;
    if (text) { x.textContent = text; }
    return x;
  }
  function tossShow() {
    var src = root.querySelector('template[data-screen-toss]');
    if (!src || document.querySelector('[data-toss-show]')) { return; }
    var key = 'sv-toss:screen:' + src.getAttribute('data-key');
    try {
      if (window.localStorage.getItem(key)) { return; }
      window.localStorage.setItem(key, '1');
    } catch (e) { /* private mode: play it anyway */ }
    var a = function (n) { return src.getAttribute('data-' + n) || ''; };
    var show = part('div', 'toss-show toss-show--tv');
    show.setAttribute('data-toss-show', '');
    show.setAttribute('role', 'status');
    var card = part('div', 'toss-show__card');
    card.appendChild(part('div', 'toss-show__eyebrow', 'The toss'));
    var coin = part('div', 'toss-show__coin');
    coin.appendChild(badge(a('logo-home'), a('name-home'), 'toss-show__face toss-show__face--front'));
    coin.appendChild(badge(a('logo-away'), a('name-away'), 'toss-show__face toss-show__face--back'));
    card.appendChild(coin);
    var won = part('div', 'toss-show__won');
    won.appendChild(badge(a('logo-' + a('winner')), a('team'), 'toss-show__logo'));
    won.appendChild(part('strong', 'toss-show__team', a('team')));
    won.appendChild(part('span', 'toss-show__line', 'won the toss'));
    card.appendChild(won);
    card.appendChild(part('div', 'toss-show__chose', 'and ' + a('chose')));
    show.appendChild(card);
    document.body.appendChild(show);
    function close() { if (show.parentNode) { show.parentNode.removeChild(show); } }
    show.addEventListener('click', close);
    show.classList.add('is-flip');
    setTimeout(function () { show.classList.add('is-won'); }, 1800);
    setTimeout(function () { show.classList.add('is-chose'); }, 4300);
    setTimeout(close, 9000);
  }

  function refresh() {
    fetch(url, { cache: 'no-store', credentials: 'same-origin', headers: etag ? { 'If-None-Match': etag } : {} })
      .then(function (r) {
        if (r.status === 304) { return null; }          // nothing changed
        if (!r.ok) { throw new Error(r.status); }
        etag = r.headers.get('ETag') || '';
        return r.text();
      })
      .then(function (html) {
        if (offline) { offline.hidden = true; }
        if (html !== null && html !== last) {             // a new clock reading counts from now
          root.innerHTML = html;
          last = html;
          shownAt = Date.now();
          tick();
          watching();
          tossShow();
        }
      })
      .catch(function () { if (offline) { offline.hidden = false; } })
      .then(function () { setTimeout(refresh, POLL_MS); });
  }

  var full = document.querySelector('[data-fullscreen]');
  if (full) {
    full.addEventListener('click', function () {
      var el = document.documentElement;
      if (el.requestFullscreen) { el.requestFullscreen().catch(function () {}); }
    });
  }

  // Keep the monitor from going to sleep while this page is showing
  var lock = null;
  function wake() {
    if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') { return; }
    navigator.wakeLock.request('screen').then(function (l) { lock = l; }).catch(function () {});
  }
  document.addEventListener('visibilitychange', function () { if (!lock || lock.released) { wake(); } });
  wake();

  setInterval(tick, 500);
  tick();
  tossShow();
  setTimeout(refresh, POLL_MS);
})();
