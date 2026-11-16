/* Keeps what changes during an event current on a page that is already open
   (UPG-267): the registration state, and on organisers' pages the counts.

   Markup: any element with data-live-event="<event id>" is a region. Inside it
     [data-live-label]        the state's label
     [data-live-label-on-change]  a badge with its own wording, replaced only when the state changes
     [data-live-explanation]  why, in a sentence (hidden while empty)
     [data-live-action]       the register / waitlist link (hidden when there is none)
     [data-live-locked]       what to show instead when nobody can register
     [data-live-action-text]  a details link whose wording follows the state
     [data-live-count="registered|checked_in|waiting|seats_free"]  organisers only
   A region with data-live-scope="ops" is answered by /live/ops.json (signed-in
   organisers); the rest by /live/state.json (public, no personal data).
   [data-live-status] anywhere on the page says when the page was last updated,
   or that it can't reach the server and is showing what it last knew
   (data-live-status="stale-only" speaks only in the second case).

   One request per scope per round, every `poll` seconds as the server asks;
   after a failure the wait doubles up to five minutes; nothing is asked while
   the tab is hidden, and the page catches up when it is shown again. */
(function () {
  'use strict';
  var BASE = 30, MAX = 300;
  var wait = BASE, timer = null, busy = false, lastOk = '', lastTry = 0, stopped = {};

  function regions(scope) {
    return Array.prototype.filter.call(document.querySelectorAll('[data-live-event]'), function (el) {
      return (el.getAttribute('data-live-scope') || 'public') === scope && !stopped[scope];
    });
  }
  function each(root, selector, fn) { Array.prototype.forEach.call(root.querySelectorAll(selector), fn); }
  function text(el, value) { if (el.textContent !== String(value)) el.textContent = String(value); }

  function apply(region, view) {
    var id = region.getAttribute('data-live-event');
    var changed = region.getAttribute('data-reg-state') !== view.key
      && region.hasAttribute('data-reg-state');
    if (region.hasAttribute('data-reg-state')) region.setAttribute('data-reg-state', view.key);
    if (region.hasAttribute('data-visitor-state')) region.setAttribute('data-visitor-state', view.key);
    each(region, '[data-reg-state]', function (el) { el.setAttribute('data-reg-state', view.key); });
    each(region, '[data-live-label]', function (el) { text(el, view.label); });
    // a badge with its own wording ("Register by 12 March") is replaced only when the state changes
    if (changed) each(region, '[data-live-label-on-change]', function (el) { text(el, view.label); });
    each(region, '[data-live-explanation]', function (el) {
      // a page that only explains a refusal keeps the line hidden while registration is open
      var show = view.explanation && !(el.hasAttribute('data-live-only-refused') && view.action);
      text(el, show ? view.explanation : '');
      el.hidden = !show;
    });
    each(region, '[data-live-action]', function (el) {
      el.hidden = !view.action;
      if (view.action) {
        el.setAttribute('href', view.action_url);
        el.setAttribute('data-reg-action', view.action);
        each(el, '[data-live-action-label]', function (label) {
          text(label, el.getAttribute('data-live-' + view.action) || view.action_label);
        });
      } else {
        el.removeAttribute('href');
      }
    });
    each(region, '[data-live-locked]', function (el) { el.hidden = !!view.action; });
    each(region, '[data-live-action-text]', function (el) {
      text(el, view.action === 'register' ? 'Details & register'
        : view.action === 'waitlist' ? 'Details & waitlist' : 'Details');
    });
    each(region, '[data-live-count]', function (el) {
      var value = view[el.getAttribute('data-live-count')];
      if (value === null || value === undefined) return;
      text(el, value);
      var holder = el.closest('[data-live-when-known]');
      if (holder) holder.hidden = false;
    });
    if (changed) {
      region.dispatchEvent(new CustomEvent('live:changed', {bubbles: true, detail: {event: id, state: view}}));
    }
  }

  function status(message, stale) {
    each(document, '[data-live-status]', function (el) {
      var quiet = el.getAttribute('data-live-status') === 'stale-only' && !stale;
      text(el, quiet ? '' : message);
      el.hidden = quiet || !message;
      el.classList.toggle('live-status--stale', !!stale);
    });
  }

  function ask(scope) {
    var found = regions(scope);
    if (!found.length) return Promise.resolve(null);
    var ids = [];
    found.forEach(function (el) {
      var id = el.getAttribute('data-live-event');
      if (id && ids.indexOf(id) === -1) ids.push(id);
    });
    var url = (scope === 'ops' ? '/live/ops.json' : '/live/state.json') + '?events=' + ids.map(encodeURIComponent).join(',');
    return fetch(url, {credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}})
      .then(function (resp) {
        if (resp.status === 401 || resp.status === 403) {
          stopped[scope] = true;    // signed out: stop asking, and say so
          return {signedOut: true};
        }
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
      })
      .then(function (data) {
        if (!data || data.signedOut) return data;
        found.forEach(function (el) {
          var view = (data.events || {})[el.getAttribute('data-live-event')];
          if (view) apply(el, view);
        });
        return data;
      });
  }

  function round() {
    if (busy || document.hidden) return;
    busy = true;
    lastTry = Date.now();
    Promise.all([ask('public'), ask('ops')]).then(function (answers) {
      var got = answers.filter(function (a) { return a && !a.signedOut; });
      var out = answers.some(function (a) { return a && a.signedOut; });
      if (got.length) {
        lastOk = got[0].at || lastOk;
        wait = Math.max(Number(got[0].poll) || BASE, 10);
      }
      if (out) status('You are signed out. Sign in again to keep these numbers up to date.', true);
      else if (got.length) status('Updated ' + lastOk, false);
    }).catch(function () {
      wait = Math.min(wait * 2, MAX);
      status(lastOk ? "Can't reach the server. Showing what was true at " + lastOk + '; trying again.'
        : "Can't reach the server; trying again.", true);
    }).then(function () {
      busy = false;
      schedule();
    });
  }

  function schedule() {
    clearTimeout(timer);
    if (document.hidden || !document.querySelector('[data-live-event]')) return;
    timer = setTimeout(round, wait * 1000);
  }

  function catchUp() {
    if (document.hidden) { clearTimeout(timer); return; }
    if (Date.now() - lastTry > 5000) round(); else schedule();
  }

  document.addEventListener('visibilitychange', catchUp);
  window.addEventListener('online', function () { wait = BASE; catchUp(); });
  window.SELive = {refresh: round, apply: apply, wait: function () { return wait; }};   // for pages that load regions later (the event popup)
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule);
  else schedule();
})();
