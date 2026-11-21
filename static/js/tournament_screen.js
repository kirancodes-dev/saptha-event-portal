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
    var now = document.querySelector('[data-screen-now]');
    if (now) {
      var d = new Date();
      now.textContent = pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
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

  setInterval(tick, 1000);
  tick();
  setTimeout(refresh, POLL_MS);
})();
