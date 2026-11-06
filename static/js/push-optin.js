/* Browser push opt-in (UPG-157). Shown only where the page includes
   includes/push_optin.html (push set up, someone logged in). The browser's
   permission prompt opens only when the button is pressed. */
(function () {
  'use strict';
  var box = document.querySelector('[data-push-optin]');
  if (!box || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return;
  var on = box.querySelector('[data-push-on]');
  var off = box.querySelector('[data-push-off]');
  var status = box.querySelector('[data-push-status]');
  var key = box.getAttribute('data-key') || '';
  if (!key) return;

  function csrf() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }
  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(body) });
  }
  function keyBytes(b64) {
    var pad = '='.repeat((4 - b64.length % 4) % 4);
    var raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function show(subscribed) {
    on.hidden = subscribed; off.hidden = !subscribed;
    status.textContent = subscribed ? 'Notifications are on for this device.' : '';
  }

  navigator.serviceWorker.ready.then(function (reg) {
    if (Notification.permission === 'denied') return;
    box.hidden = false;
    reg.pushManager.getSubscription().then(function (sub) { show(!!sub); });
    on.addEventListener('click', function () {
      Notification.requestPermission().then(function (perm) {
        if (perm !== 'granted') { status.textContent = 'Notifications were not allowed.'; return null; }
        return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
      }).then(function (sub) {
        if (!sub) return;
        return post('/push/subscribe', sub.toJSON()).then(function (r) {
          if (r.ok) show(true); else status.textContent = 'Could not turn on notifications.';
        });
      }).catch(function () { status.textContent = 'Could not turn on notifications.'; });
    });
    off.addEventListener('click', function () {
      reg.pushManager.getSubscription().then(function (sub) {
        if (!sub) { show(false); return; }
        var endpoint = sub.endpoint;
        return sub.unsubscribe().then(function () { return post('/push/unsubscribe', { endpoint: endpoint }); })
          .then(function () { show(false); });
      });
    });
  });
})();
