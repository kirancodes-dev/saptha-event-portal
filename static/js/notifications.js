/* The notification bell in the app bar (UPG-63): opens a panel with the 20
   latest notifications from /notifications/feed; "Mark all read" posts to
   /notifications/mark_all_read. The unread count badge (#notif-badge) is kept
   up to date by global.js. Titles and bodies are text (BLK-19). */
(function () {
  // A notification link may be a path on this site or an https address;
  // anything else (javascript:, data:, protocol-relative) isn't linked.
  function isSafeLink(link) {
    var v = String(link).trim();
    return (v.charAt(0) === '/' && v.charAt(1) !== '/' && v.charAt(1) !== '\\') || /^https:\/\//i.test(v);
  }

  'use strict';
  var open = false, loaded = false;

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }

  function row(n) {
    var a = document.createElement(n.link ? 'a' : 'div');
    a.className = 'notif-item' + (n.read ? '' : ' is-unread');
    if (n.link && isSafeLink(n.link)) a.href = n.link;
    var t = document.createElement('div'); t.className = 'notif-item__title'; t.textContent = n.title || '';
    var b = document.createElement('div'); b.className = 'notif-item__body'; b.textContent = n.body || '';
    a.appendChild(t); a.appendChild(b);
    return a;
  }

  function load() {
    var list = document.getElementById('notif-list');
    if (!list) return;
    fetch('/notifications/feed', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (items) {
        list.replaceChildren();
        if (!Array.isArray(items) || !items.length) {
          var e = document.createElement('div'); e.className = 'notif-empty'; e.textContent = 'No notifications yet.';
          list.appendChild(e);
          return;
        }
        items.forEach(function (n) { list.appendChild(row(n)); });
      })
      .catch(function () {
        list.replaceChildren();
        var e = document.createElement('div'); e.className = 'notif-empty'; e.textContent = 'Could not load notifications.';
        list.appendChild(e);
      });
  }

  function setOpen(v) {
    var panel = document.getElementById('notif-panel');
    var btn = document.getElementById('bell-btn');
    if (!panel) return;
    open = v;
    panel.hidden = !v;
    if (btn) btn.setAttribute('aria-expanded', v ? 'true' : 'false');
    if (v && !loaded) { load(); loaded = true; }
  }

  window.toggleNotifPanel = function () { setOpen(!open); };
  window.markAllRead = function () {
    fetch('/notifications/mark_all_read', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } })
      .then(function () { load(); if (window.updateNotificationBadge) window.updateNotificationBadge(); });
  };

  document.addEventListener('click', function (e) {
    var wrap = document.getElementById('notif-wrap');
    if (open && wrap && !wrap.contains(e.target)) setOpen(false);
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && open) setOpen(false); });

  Object.assign(window.SE_H = window.SE_H || {}, {
    'notif:toggle': function () { window.toggleNotifPanel(); },
    'notif:mark-all': function () { window.markAllRead(); }
  });
})();
