// The hackathon page (UPG-196): countdowns, and a poll every 60 seconds that
// reloads the page when something on it has changed. No SSE: a poll holds no
// server thread.
(function () {
    'use strict';
    var root = document.getElementById('hkPortal');
    if (!root) { return; }

    function left(ms) {
        if (ms <= 0) { return 'now'; }
        var s = Math.floor(ms / 1000);
        var d = Math.floor(s / 86400); s -= d * 86400;
        var h = Math.floor(s / 3600); s -= h * 3600;
        var m = Math.floor(s / 60); s -= m * 60;
        var parts = [];
        if (d) { parts.push(d + 'd'); }
        if (d || h) { parts.push(h + 'h'); }
        parts.push(m + 'm');
        if (!d) { parts.push(s + 's'); }
        return parts.join(' ') + ' left';
    }

    var offset = 0;   // server clock minus this browser's clock
    function tick() {
        var now = Date.now() + offset;
        document.querySelectorAll('[data-countdown]').forEach(function (el) {
            var at = Date.parse(el.getAttribute('data-countdown'));
            if (!isNaN(at)) { el.textContent = left(at - now); }
            if (!isNaN(at) && at - now <= 0 && !el.dataset.reloaded) {
                el.dataset.reloaded = '1';
                setTimeout(function () { window.location.reload(); }, 1500);
            }
        });
    }
    tick();
    setInterval(tick, 1000);

    var url = root.getAttribute('data-state-url');
    var version = root.getAttribute('data-version');
    function poll() {
        if (document.hidden) { return; }
        fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (state) {
                if (!state) { return; }
                if (state.now) { offset = Date.parse(state.now) - Date.now(); }
                var typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
                if (state.version && state.version !== version && !typing) { window.location.reload(); }
            })
            .catch(function () { /* offline: try again next minute */ });
    }
    poll();
    setInterval(poll, 60000);
})();
