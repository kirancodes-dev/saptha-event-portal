/**
 * i18n.js — Client-side internationalization for SapthaEvent
 * ----------------------------------------------------------
 * • Fetches translations from /api/translations
 * • Applies them to elements with  data-i18n="key"
 * • Supports  data-i18n-placeholder, data-i18n-title, data-i18n-aria  attrs
 * • Persists locale in localStorage + cookie
 * • Toggles dir="rtl" on <html> for Arabic
 */

(function () {
  'use strict';

  var STORAGE_KEY  = 'saptha_locale';
  var COOKIE_NAME  = 'locale';
  var API_BASE     = '/api/translations';
  var LOCALES_API  = '/api/locales';

  // ── Cache ──────────────────────────────────────────────────────────
  var _cache    = {};        // { locale: { key: text } }
  var _current  = null;
  var _rtlCodes = ['ar'];    // locales that use RTL

  // ── Public API ─────────────────────────────────────────────────────
  window.SapthaI18n = {
    init:           init,
    setLocale:      setLocale,
    getLocale:      getLocale,
    t:              translate,
    applyAll:       applyTranslations,
    onLocaleChange: null,     // optional callback(locale)
  };

  // ── Initialise ─────────────────────────────────────────────────────
  function init() {
    _current = getSavedLocale() || getDocLocale() || 'en';
    fetchAndApply(_current);
    bindSelectors();
  }

  // ── Locale resolution ──────────────────────────────────────────────
  function getSavedLocale() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }

  function getDocLocale() {
    var html = document.documentElement;
    return html.getAttribute('lang') || null;
  }

  function getLocale() {
    return _current || 'en';
  }

  // ── Persistence ────────────────────────────────────────────────────
  function persistLocale(locale) {
    try { localStorage.setItem(STORAGE_KEY, locale); } catch (_) { /* noop */ }
    document.cookie = COOKIE_NAME + '=' + locale +
      ';path=/;max-age=' + (365 * 24 * 60 * 60) + ';SameSite=Lax';
  }

  // ── Set locale ─────────────────────────────────────────────────────
  function setLocale(locale) {
    if (locale === _current) return;
    _current = locale;
    persistLocale(locale);
    fetchAndApply(locale);

    if (typeof window.SapthaI18n.onLocaleChange === 'function') {
      window.SapthaI18n.onLocaleChange(locale);
    }
  }

  // ── Fetch & apply ──────────────────────────────────────────────────
  function fetchAndApply(locale) {
    if (_cache[locale]) {
      applyTranslations(_cache[locale], locale);
      return;
    }

    var url = API_BASE + '?locale=' + encodeURIComponent(locale);

    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        _cache[locale] = data;
        applyTranslations(data, locale);
      })
      .catch(function (err) {
        console.warn('[i18n] Failed to load translations for', locale, err);
      });
  }

  // ── DOM translation ────────────────────────────────────────────────
  function applyTranslations(dict, locale) {
    if (!dict) return;

    // data-i18n  → textContent
    var els = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
      var key = els[i].getAttribute('data-i18n');
      if (dict[key]) els[i].textContent = dict[key];
    }

    // data-i18n-placeholder  → placeholder attr
    var phs = document.querySelectorAll('[data-i18n-placeholder]');
    for (var j = 0; j < phs.length; j++) {
      var pk = phs[j].getAttribute('data-i18n-placeholder');
      if (dict[pk]) phs[j].setAttribute('placeholder', dict[pk]);
    }

    // data-i18n-title  → title attr
    var tts = document.querySelectorAll('[data-i18n-title]');
    for (var k = 0; k < tts.length; k++) {
      var tk = tts[k].getAttribute('data-i18n-title');
      if (dict[tk]) tts[k].setAttribute('title', dict[tk]);
    }

    // data-i18n-aria  → aria-label attr
    var als = document.querySelectorAll('[data-i18n-aria]');
    for (var l = 0; l < als.length; l++) {
      var ak = als[l].getAttribute('data-i18n-aria');
      if (dict[ak]) als[l].setAttribute('aria-label', dict[ak]);
    }

    // data-i18n-html  → innerHTML  (use with caution — trusted strings only)
    var hls = document.querySelectorAll('[data-i18n-html]');
    for (var m = 0; m < hls.length; m++) {
      var hk = hls[m].getAttribute('data-i18n-html');
      if (dict[hk]) hls[m].innerHTML = dict[hk];
    }

    // RTL toggle
    toggleRTL(locale);

    // Update <html lang>
    document.documentElement.setAttribute('lang', locale || 'en');
  }

  // ── Translate single key ───────────────────────────────────────────
  function translate(key) {
    var dict = _cache[_current];
    if (dict && dict[key]) return dict[key];
    return key;  // fallback: return the key itself
  }

  // ── RTL support ────────────────────────────────────────────────────
  function toggleRTL(locale) {
    var html = document.documentElement;
    if (_rtlCodes.indexOf(locale) !== -1) {
      html.setAttribute('dir', 'rtl');
      html.classList.add('rtl');
    } else {
      html.setAttribute('dir', 'ltr');
      html.classList.remove('rtl');
    }
  }

  // ── Bind language-selector links ───────────────────────────────────
  function bindSelectors() {
    // Handle clicks on  [data-locale]  links / buttons
    document.addEventListener('click', function (e) {
      var target = e.target.closest('[data-locale]');
      if (!target) return;

      // If the link points to /set-language/ we let the server handle
      // it (full page redirect).  For SPA-style switching, prevent
      // default and use client-side swap:
      var href = target.getAttribute('href') || '';
      if (href.indexOf('/set-language/') === -1) {
        e.preventDefault();
        var locale = target.getAttribute('data-locale');
        if (locale) setLocale(locale);
      }
      // else: let the browser follow the link normally
    });
  }

  // ── Auto-init on DOMContentLoaded ──────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
