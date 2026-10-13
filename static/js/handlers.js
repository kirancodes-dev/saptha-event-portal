/*
 * handlers.js — event handlers without inline attributes (UPG-25).
 *
 * The CSP allows no inline script, so `onclick="…"` attributes can't run.
 * Templates mark elements with `data-h-<event>="<key>"` instead, and each
 * template's handler file (static/js/handlers/*.js) registers the original
 * code under that key in SE_H. This file binds them:
 *   - on DOMContentLoaded, and for elements added later (MutationObserver);
 *   - `this` is the element and `event` the event, as in an inline handler;
 *   - returning false prevents the default action, as in an inline handler;
 *   - an <img> that already loaded or failed before binding gets its
 *     load/error handler called once; <body data-h-load> waits for window load.
 * Values a template rendered into the old attribute travel as data-h-a0,
 * data-h-a1, … and the code reads them from this.dataset.
 */
(function () {
  'use strict';
  window.SE_H = window.SE_H || {};
  // Small actions that scripts build into HTML strings (they can't carry code).
  Object.assign(window.SE_H, {
    'se:remove-parent': function () { this.parentElement.remove(); },
    'se:remove-grandparent': function () { this.parentElement.parentElement.remove(); },
    'se:remove-closest': function () { var t = this.closest(this.dataset.closest); if (t) t.remove(); },
    'se:hide': function () { this.style.display = 'none'; },
    'se:go': function () { window.location.href = this.dataset.href; },
    // "Go back" links: back in history when there is one, else the link's own href
    'se:back': function () { if (window.history.length > 1) { window.history.back(); return false; } },
    'se:call': function (event) {
      // data-call="fnName" data-args='["a", 1]' — this element is passed last
      var fn = window[this.dataset.call];
      var args = this.dataset.args ? JSON.parse(this.dataset.args) : [];
      if (typeof fn === 'function') return fn.apply(this, args.concat([this, event]));
    }
  });
  var PREFIX = 'data-h-';
  var BOUND = '__seHandlersBound';

  function run(el, fn, event) {
    var result = fn.call(el, event);
    if (result === false && event && event.preventDefault) {
      event.preventDefault();
    }
    return result;
  }

  function bind(el) {
    if (!el || el.nodeType !== 1 || !el.attributes) return;
    var done = el[BOUND] || (el[BOUND] = {});
    for (var i = 0; i < el.attributes.length; i++) {
      var attr = el.attributes[i];
      var name = attr.name;
      if (name.indexOf(PREFIX) !== 0 || /^data-h-a\d+$/.test(name)) continue;
      var type = name.slice(PREFIX.length);
      var key = attr.value;
      if (done[type] === key) continue;
      var fn = window.SE_H[key];
      if (typeof fn !== 'function') {
        if (window.console) console.warn('handlers.js: no handler registered for', key);
        continue;
      }
      done[type] = key;
      (function (fn, type) {
        if (el.tagName === 'BODY' && type === 'load') {
          if (document.readyState === 'complete') { run(el, fn, new Event('load')); }
          else { window.addEventListener('load', function (e) { run(el, fn, e); }); }
          return;
        }
        el.addEventListener(type, function (e) { return run(el, fn, e); });
        if (el.tagName === 'IMG' && el.complete) {
          if (type === 'error' && el.getAttribute('src') && el.naturalWidth === 0) run(el, fn, new Event('error'));
          if (type === 'load' && el.naturalWidth > 0) run(el, fn, new Event('load'));
        }
      })(fn, type);
    }
  }

  function bindTree(root) {
    if (!root || root.nodeType !== 1) return;
    bind(root);
    var all = root.getElementsByTagName('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      for (var j = 0; j < el.attributes.length; j++) {
        if (el.attributes[j].name.indexOf(PREFIX) === 0) { bind(el); break; }
      }
    }
  }

  window.SE_bindHandlers = bindTree;

  function start() {
    bindTree(document.documentElement);
    if (!window.MutationObserver) return;
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        r.addedNodes.forEach(function (n) { bindTree(n); });
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
