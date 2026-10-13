/*
 * forms.js — one submit per click on every form (UPG-26).
 *
 * When a form is sent (and no page script stopped it), its submit buttons are
 * disabled and show "Please wait…", and a second submit of the same form (a
 * double click, Enter pressed twice) is ignored. Buttons are disabled just
 * after the browser has collected the form's fields, so a clicked button's
 * name/value is still sent. They come back when the page is shown again from
 * the back/forward cache, and after 10 seconds for forms that don't leave the
 * page (downloads, new tabs). Forms marked data-guard="until-result" stay
 * locked until the page changes. data-no-guard opts a form out.
 * The server makes registration idempotent too (submission_id).
 */
(function () {
  'use strict';
  var REENABLE_MS = 10000;
  var SUBMITS = 'button[type="submit"], button:not([type]), input[type="submit"]';

  function buttonsOf(form) {
    var list = Array.prototype.slice.call(form.querySelectorAll(SUBMITS));
    if (form.id) {
      list = list.concat(Array.prototype.slice.call(
        document.querySelectorAll('[form="' + form.id + '"]')).filter(function (b) { return b.matches(SUBMITS); }));
    }
    return list;
  }

  function lock(form) {
    form.dataset.submitting = '1';
    form.setAttribute('aria-busy', 'true');
    buttonsOf(form).forEach(function (b) {
      if (b.disabled) return;
      b.disabled = true;
      b.dataset.seGuarded = '1';
      if (b.tagName === 'BUTTON' && !b.hasAttribute('data-no-loader')) {
        b.dataset.seLabel = b.textContent;
        var spinner = document.createElement('span');
        spinner.className = 'se-spinner';
        spinner.setAttribute('aria-hidden', 'true');
        var textNode = document.createTextNode(' ' + (b.dataset.loadingText || 'Please wait…'));
        b.replaceChildren(spinner, textNode);
      }
    });
  }

  function unlock(form) {
    delete form.dataset.submitting;
    form.removeAttribute('aria-busy');
    buttonsOf(form).forEach(function (b) {
      if (!b.dataset.seGuarded) return;
      b.disabled = false;
      delete b.dataset.seGuarded;
      if (b.dataset.seLabel !== undefined) {
        b.textContent = b.dataset.seLabel;
        delete b.dataset.seLabel;
      }
    });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-no-guard')) return;
    if (form.dataset.submitting === '1') { e.preventDefault(); return; }
    if (e.defaultPrevented) return;   // a page script sends it itself
    setTimeout(function () { lock(form); }, 0);
    if (form.dataset.guard !== 'until-result') {
      setTimeout(function () { if (document.contains(form)) unlock(form); }, REENABLE_MS);
    }
  });

  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    document.querySelectorAll('form[data-submitting]').forEach(unlock);
  });

  window.SE_unlockForm = unlock;
})();
