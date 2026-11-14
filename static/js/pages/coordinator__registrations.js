// The SPOC's registrations page (UPG-234). The page loads no Bootstrap
// script, so its own buttons work here: each row's Details, "Show all
// details", the Cancel, Delete and Accept dialogs (native <dialog>), and the
// fold-away sections (<details>) remember whether they were open.
(function () {
  'use strict';

  function target(el) {
    var sel = el.getAttribute('data-bs-target');
    return sel ? document.querySelector(sel) : null;
  }

  function setRow(btn, open) {
    var row = target(btn);
    if (!row) return;
    row.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    var label = btn.querySelector('[data-label]');
    if (label) label.textContent = open ? 'Hide details' : 'Details';
  }

  function setAll(btn, open) {
    var scope = btn.closest('section') || document;
    scope.querySelectorAll('[data-toggle-row]').forEach(function (b) { setRow(b, open); });
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    var label = btn.querySelector('[data-label]');
    if (label) label.textContent = open ? 'Hide all details' : 'Show all details';
  }

  document.addEventListener('click', function (e) {
    var row = e.target.closest('[data-toggle-row]');
    if (row) { setRow(row, row.getAttribute('aria-expanded') !== 'true'); return; }

    var all = e.target.closest('[data-details-all]');
    if (all) { setAll(all, all.getAttribute('aria-expanded') !== 'true'); return; }

    var opener = e.target.closest('[data-dialog-open]');
    if (opener) {
      var dialog = target(opener);
      if (dialog && typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
      return;
    }

    var closer = e.target.closest('[data-dialog-close]');
    if (closer) {
      var d = closer.closest('dialog');
      if (d) d.close();
      return;
    }

    // A click on the dimmed area around a dialog closes it
    if (e.target.tagName === 'DIALOG' && e.target.open) {
      var r = e.target.getBoundingClientRect();
      var inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (!inside) e.target.close();
    }
  });

  // Fold-away sections stay as the SPOC left them while they work on the page
  document.querySelectorAll('details[data-remember]').forEach(function (d) {
    var key = 'reg-page:' + location.pathname + ':' + d.getAttribute('data-remember');
    try {
      var saved = sessionStorage.getItem(key);
      if (saved === 'open') d.open = true;
      else if (saved === 'closed') d.open = false;
    } catch (err) { /* storage off: the default */ }
    d.addEventListener('toggle', function () {
      try { sessionStorage.setItem(key, d.open ? 'open' : 'closed'); } catch (err) { /* storage off */ }
    });
  });

  // A link to a folded section (the "on the waitlist" badge, #waitlist) opens it
  function openTo(hash) {
    if (!hash || hash.length < 2) return;
    var el = null;
    try { el = document.querySelector(hash); } catch (err) { return; }
    var fold = el && (el.tagName === 'DETAILS' ? el : el.closest('details'));
    if (fold && !fold.open) fold.open = true;
  }
  openTo(location.hash);
  window.addEventListener('hashchange', function () { openTo(location.hash); });
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="#"]');
    if (a) openTo(a.getAttribute('href'));
  });

  // UPG-265: copy the WhatsApp message, to paste into a group or a chat
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy-share]');
    if (!btn) return;
    var pre = document.querySelector('[data-share-text]');
    var label = btn.querySelector('[data-label]');
    if (!pre || !navigator.clipboard) return;
    navigator.clipboard.writeText(pre.textContent).then(function () {
      if (label) label.textContent = 'Copied';
      setTimeout(function () { if (label) label.textContent = 'Copy the message'; }, 2000);
    });
  });
})();
