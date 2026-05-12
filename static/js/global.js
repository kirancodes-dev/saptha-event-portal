/* ==========================================================================
   SapthaEvent — Global JS
   Loaded on every page. No dependencies (pure vanilla).
   ========================================================================== */

(function () {
  'use strict';

  /* ── 1. TOP PAGE PROGRESS BAR ─────────────────────────────────────────── */
  const bar = document.createElement('div');
  bar.id = 'sp-progress';
  bar.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'width:0', 'height:3px',
    'background:linear-gradient(90deg,#c9a45e,#f5c878,#c9a45e)',
    'background-size:200% 100%',
    'animation:sp-shimmer 1.4s linear infinite',
    'z-index:99999', 'transition:width .3s ease,opacity .4s ease',
    'pointer-events:none', 'opacity:0',
  ].join(';');
  document.documentElement.appendChild(bar);

  const style = document.createElement('style');
  style.textContent = `
    @keyframes sp-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
  `;
  document.head.appendChild(style);

  function progressStart() {
    bar.style.opacity = '1';
    bar.style.width = '0';
    requestAnimationFrame(() => { bar.style.width = '70%'; });
  }
  function progressDone() {
    bar.style.width = '100%';
    setTimeout(() => { bar.style.opacity = '0'; bar.style.width = '0'; }, 400);
  }

  window.addEventListener('beforeunload', progressStart);
  window.addEventListener('load', progressDone);
  document.addEventListener('DOMContentLoaded', progressDone);

  // Intercept link clicks for the progress bar
  document.addEventListener('click', function (e) {
    const a = e.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript') ||
        href.startsWith('mailto') || href.startsWith('tel') ||
        a.target === '_blank' || e.ctrlKey || e.metaKey || e.shiftKey) return;
    progressStart();
  });

  /* ── 2. TOAST NOTIFICATIONS ───────────────────────────────────────────── */
  const toastContainer = document.createElement('div');
  toastContainer.id = 'sp-toast-container';
  toastContainer.style.cssText = [
    'position:fixed', 'top:72px', 'right:16px', 'z-index:99998',
    'display:flex', 'flex-direction:column', 'gap:8px',
    'max-width:min(380px,calc(100vw - 32px))', 'pointer-events:none',
  ].join(';');
  document.body.appendChild(toastContainer);

  const toastIcons = {
    success: '<i class="fas fa-check-circle" style="color:#10b981"></i>',
    danger:  '<i class="fas fa-times-circle" style="color:#ef4444"></i>',
    error:   '<i class="fas fa-times-circle" style="color:#ef4444"></i>',
    warning: '<i class="fas fa-exclamation-triangle" style="color:#f59e0b"></i>',
    info:    '<i class="fas fa-info-circle" style="color:#3b82f6"></i>',
  };

  window.showToast = function (message, type, duration) {
    type = type || 'info';
    duration = duration === undefined ? 4000 : duration;

    const t = document.createElement('div');
    t.style.cssText = [
      'background:#fff', 'border-radius:12px',
      'box-shadow:0 8px 24px rgba(11,21,48,.14),0 2px 6px rgba(11,21,48,.08)',
      'padding:12px 14px', 'display:flex', 'align-items:flex-start', 'gap:10px',
      'font-size:13.5px', 'font-weight:500', 'color:#1e293b',
      'pointer-events:auto', 'cursor:pointer',
      'border-left:4px solid',
      'opacity:0', 'transform:translateX(24px)',
      'transition:opacity .25s ease,transform .25s ease',
      'word-break:break-word', 'line-height:1.45',
    ].join(';');

    const borderColors = {success:'#10b981', danger:'#ef4444', error:'#ef4444',
                          warning:'#f59e0b', info:'#3b82f6'};
    t.style.borderLeftColor = borderColors[type] || '#3b82f6';

    t.innerHTML = `
      <span style="flex-shrink:0;font-size:16px;margin-top:1px">${toastIcons[type] || toastIcons.info}</span>
      <span style="flex:1">${message}</span>
      <button onclick="this.closest('[id^=sp-t]').remove()" style="background:none;border:none;cursor:pointer;color:#94a3b8;padding:0 0 0 6px;font-size:15px;line-height:1;flex-shrink:0" aria-label="Dismiss">&times;</button>
    `;
    t.id = 'sp-t-' + Date.now();
    toastContainer.appendChild(t);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => { t.style.opacity = '1'; t.style.transform = 'none'; });
    });

    function dismiss() {
      t.style.opacity = '0';
      t.style.transform = 'translateX(24px)';
      setTimeout(() => t.remove(), 260);
    }
    t.addEventListener('click', dismiss);
    if (duration > 0) setTimeout(dismiss, duration);
  };

  /* ── 3. CONVERT FLASK FLASH MESSAGES → TOASTS ─────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.alert, .flash').forEach(function (el) {
      const text = el.innerText.trim();
      if (!text) return;
      let type = 'info';
      const cls = el.className;
      if (/success/.test(cls)) type = 'success';
      else if (/danger|error/.test(cls)) type = 'danger';
      else if (/warning/.test(cls)) type = 'warning';
      showToast(text, type, 5000);
      el.style.display = 'none'; // hide the static alert
    });
  });

  /* ── 4. BUTTON LOADING STATE ──────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function () {
        const btn = form.querySelector('[type="submit"]');
        if (!btn || btn.dataset.noLoader) return;
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.dataset.originalHtml = original;
        btn.innerHTML = `<span class="sp-spinner"></span> ${btn.dataset.loadingText || 'Please wait…'}`;

        // Safety: re-enable after 15s in case server never responds
        setTimeout(function () {
          if (btn.disabled) {
            btn.disabled = false;
            btn.innerHTML = original;
          }
        }, 15000);
      });
    });
  });

  /* ── 5. BACK TO TOP BUTTON ────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    const btt = document.createElement('button');
    btt.id = 'sp-btt';
    btt.setAttribute('aria-label', 'Back to top');
    btt.innerHTML = '<i class="fas fa-chevron-up"></i>';
    btt.style.cssText = [
      'position:fixed', 'bottom:24px', 'left:24px', 'width:42px', 'height:42px',
      'border-radius:50%', 'border:none', 'cursor:pointer',
      'background:linear-gradient(135deg,#1a2557,#2a3a7a)',
      'color:#fff', 'font-size:14px', 'z-index:9990',
      'box-shadow:0 4px 14px rgba(26,37,87,.35)',
      'display:flex', 'align-items:center', 'justify-content:center',
      'opacity:0', 'transform:translateY(10px)',
      'transition:opacity .25s,transform .25s',
      'pointer-events:none',
    ].join(';');
    document.body.appendChild(btt);

    window.addEventListener('scroll', function () {
      const show = window.scrollY > 300;
      btt.style.opacity = show ? '1' : '0';
      btt.style.transform = show ? 'none' : 'translateY(10px)';
      btt.style.pointerEvents = show ? 'auto' : 'none';
    }, { passive: true });

    btt.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  /* ── 6. ANIMATED COUNTERS ─────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    const counters = document.querySelectorAll('.counter[data-target]');
    if (!counters.length) return;

    const easeOut = function (t) { return 1 - Math.pow(1 - t, 3); };

    function animateCounter(el) {
      const target = parseInt(el.dataset.target, 10);
      if (isNaN(target)) return;
      const duration = 1400;
      const start = performance.now();
      function step(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        el.textContent = Math.round(easeOut(progress) * target).toLocaleString();
        if (progress < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }

    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateCounter(entry.target);
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.3 });
      counters.forEach(function (el) { obs.observe(el); });
    } else {
      counters.forEach(animateCounter);
    }
  });

  /* ── 7. AUTO-FOCUS FIRST EMPTY FORM INPUT ─────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    if (window.matchMedia('(pointer: fine)').matches) {
      const inp = document.querySelector(
        'form:not([data-no-autofocus]) input:not([type=hidden]):not([type=submit]):not([disabled])'
      );
      if (inp && !inp.value) inp.focus();
    }
  });

  /* ── 8. RIPPLE EFFECT ON BUTTONS ──────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.btn, button:not([data-no-ripple])');
    if (!btn || btn.dataset.noRipple) return;
    const r = document.createElement('span');
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    r.style.cssText = [
      'position:absolute', 'border-radius:50%', 'pointer-events:none',
      `width:${size}px`, `height:${size}px`,
      `top:${e.clientY - rect.top - size / 2}px`,
      `left:${e.clientX - rect.left - size / 2}px`,
      'background:rgba(255,255,255,0.22)',
      'transform:scale(0)', 'animation:sp-ripple .5s ease-out forwards',
    ].join(';');
    if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative';
    btn.style.overflow = 'hidden';
    btn.appendChild(r);
    setTimeout(() => r.remove(), 550);
  });

  const rippleStyle = document.createElement('style');
  rippleStyle.textContent = `@keyframes sp-ripple{to{transform:scale(1);opacity:0}}`;
  document.head.appendChild(rippleStyle);

  /* ── 9. CONFIRM DIALOGS (data-confirm attribute) ───────────────────────── */
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-confirm]');
    if (!el) return;
    const msg = el.dataset.confirm || 'Are you sure?';
    if (!confirm(msg)) e.preventDefault();
  });

  /* ── 10. MOBILE NAV — close on outside click ──────────────────────────── */
  document.addEventListener('click', function (e) {
    const toggler = document.querySelector('.navbar-toggler');
    const collapse = document.querySelector('.navbar-collapse.show');
    if (collapse && toggler && !collapse.contains(e.target) && !toggler.contains(e.target)) {
      toggler.click();
    }
  });

  /* ── 11. LAZY-LOAD IMAGES ─────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    if ('IntersectionObserver' in window) {
      const imgs = document.querySelectorAll('img[data-src]');
      const imgObs = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
            imgObs.unobserve(img);
          }
        });
      });
      imgs.forEach(function (img) { imgObs.observe(img); });
    }
  });

  /* ── 12. COPY-TO-CLIPBOARD (data-copy) ────────────────────────────────── */
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-copy]');
    if (!el) return;
    const text = el.dataset.copy || el.innerText;
    navigator.clipboard.writeText(text).then(function () {
      showToast('Copied to clipboard!', 'success', 2000);
    }).catch(function () {
      showToast('Could not copy — please copy manually.', 'warning', 3000);
    });
  });

})();
