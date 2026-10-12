/* ==========================================================================
   SapthaEvent — Global JS (Unified & Consolidated)
   Replaces: global.js and design_system.js
   Loaded on every page. No external dependencies (pure vanilla JS + Bootstrap 5 helper integration).
   ========================================================================== */

(function () {
  'use strict';

  /* ── 1. THEME MANAGEMENT (DARK / LIGHT MODE) ────────────────────────── */
  function initTheme() {
    const saved = localStorage.getItem('ds-theme');
    // Light is the portal's theme; dark is only used when someone picks it (UPG-63)
    const theme = saved === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeToggleUI(theme);

  }

  function updateThemeToggleUI(theme) {
    const icon = document.querySelector('#theme-toggle-icon');
    if (icon) {
      icon.innerHTML = theme === 'dark' ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    }
    const text = document.querySelector('#theme-toggle-text');
    if (text) {
      text.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
    }
  }

  window.toggleTheme = function () {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    
    const changeTheme = () => {
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ds-theme', next);
      updateThemeToggleUI(next);
      showToast(`Switched to ${next} theme`, 'info', 1500);
    };

    if (document.startViewTransition) {
      document.startViewTransition(changeTheme);
    } else {
      changeTheme();
    }
  };

  // Run immediately to prevent flash of wrong theme
  initTheme();

  /* ── 2. TOP PAGE PROGRESS BAR ─────────────────────────────────────────── */
  const bar = document.createElement('div');
  bar.id = 'sp-progress';
  bar.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'width:0', 'height:3px',
    'background:var(--brand-gold,#c69d67)',
    'z-index:99999', 'transition:width .3s ease,opacity .4s ease',
    'pointer-events:none', 'opacity:0',
  ].join(';');
  document.documentElement.appendChild(bar);

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

  // Intercept link clicks for progress bar
  document.addEventListener('click', function (e) {
    const a = e.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript') ||
        href.startsWith('mailto') || href.startsWith('tel') ||
        a.target === '_blank' || e.ctrlKey || e.metaKey || e.shiftKey) return;
    progressStart();
  });

  /* ── 3. TOAST NOTIFICATIONS ───────────────────────────────────────────
     Styled by .se-toast in global.css (UPG-63); top-right on every page. */
  let toastContainer = document.querySelector('#sp-toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'sp-toast-container';
    toastContainer.setAttribute('role', 'status');
    toastContainer.setAttribute('aria-live', 'polite');
    document.body.appendChild(toastContainer);
  }

  const toastIcons = {
    success: 'fa-check-circle', danger: 'fa-times-circle', error: 'fa-times-circle',
    warning: 'fa-exclamation-triangle', info: 'fa-info-circle',
  };

  window.showToast = function (message, type, duration) {
    type = type || 'info';
    if (type === 'error') type = 'danger';
    if (!toastIcons[type]) type = 'info';
    duration = duration === undefined ? 4000 : duration;

    const t = document.createElement('div');
    t.className = 'se-toast se-toast--' + type;
    // Built as DOM nodes: the message is always text, never HTML (BLK-19)
    const icon = document.createElement('i');
    icon.className = 'se-toast__icon fas ' + toastIcons[type];
    icon.setAttribute('aria-hidden', 'true');
    const msg = document.createElement('span');
    msg.className = 'se-toast__msg';
    msg.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'se-toast__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '\u00d7';
    t.append(icon, msg, close);
    t.id = 'sp-t-' + Date.now();
    toastContainer.appendChild(t);
    requestAnimationFrame(() => { requestAnimationFrame(() => t.classList.add('is-shown')); });

    function dismiss() {
      t.classList.remove('is-shown');
      setTimeout(() => t.remove(), 220);
    }
    t.addEventListener('click', dismiss);
    if (duration > 0) setTimeout(dismiss, duration);
  };

  // Expose DS.toast for backward compatibility with design_system.js references
  window.DS = {
    toast(message, type = 'info', duration = 4000) {
      window.showToast(message, type, duration);
    },
    showLoading(message) {
      window.showLoading(message);
    },
    hideLoading() {
      window.hideLoading();
    }
  };

  /* ── 4. CONVERT FLASK FLASH MESSAGES → TOASTS ─────────────────────────
     Only real flash messages (includes/flash_messages.html marks them with
     data-flash). Static .alert boxes are page content and stay put (UPG-63). */
  function processFlashMessages() {
    document.querySelectorAll('[data-flash], .flash').forEach(function (el) {
      const text = el.textContent.trim();
      if (!text) return;
      const raw = el.dataset.flashType || el.className;
      let type = 'info';
      if (/success/.test(raw)) type = 'success';
      else if (/danger|error/.test(raw)) type = 'danger';
      else if (/warning/.test(raw)) type = 'warning';
      showToast(text, type, 6000);
      el.remove();
    });
    document.querySelectorAll('.flash-stack').forEach(function (el) {
      if (!el.children.length) el.remove();
    });
  }
  document.addEventListener('DOMContentLoaded', processFlashMessages);

  /* ── 5. BUTTON LOADING STATE ──────────────────────────────────────────
     Moved to static/js/forms.js, which every page loads (UPG-26). */

  /* ── 6. BACK TO TOP BUTTON ────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    const btt = document.createElement('button');
    btt.id = 'sp-btt';
    btt.setAttribute('aria-label', 'Back to top');
    btt.innerHTML = '<i class="fas fa-chevron-up"></i>';
    btt.style.cssText = [
      'position:fixed', 'bottom:24px', 'left:24px', 'width:42px', 'height:42px',
      'border-radius:50%', 'border:none', 'cursor:pointer',
      'background:var(--brand-navy,#00185e)',
      'color:#fff', 'font-size:14px', 'z-index:9990',
      'box-shadow:var(--shadow-md)',
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

  /* ── 7. ANIMATED COUNTERS & SCROLL ANIMATIONS ────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    const counters = document.querySelectorAll('.counter[data-target]');
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

    // Scroll Animations (Intersection Observer)
    if ('IntersectionObserver' in window) {
      // Counters Observer
      if (counters.length) {
        const counterObs = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              animateCounter(entry.target);
              counterObs.unobserve(entry.target);
            }
          });
        }, { threshold: 0.2 });
        counters.forEach(function (el) { counterObs.observe(el); });
      }

      // Animate-on-scroll elements
      const scrollAnimObs = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            scrollAnimObs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });

      document.querySelectorAll('.animate-on-scroll').forEach(function (el) {
        scrollAnimObs.observe(el);
      });
    } else {
      // Fallback
      counters.forEach(animateCounter);
      document.querySelectorAll('.animate-on-scroll').forEach(function (el) {
        el.classList.add('visible');
      });
    }
  });

  /* ── 8. AUTO-FOCUS FIRST EMPTY FORM INPUT ─────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    if (window.matchMedia('(pointer: fine)').matches) {
      const inp = document.querySelector(
        'form:not([data-no-autofocus]) input:not([type=hidden]):not([type=submit]):not([disabled])'
      );
      if (inp && !inp.value) inp.focus();
    }
  });

  /* ── 9. (Button ripple retired in UPG-63: buttons use plain hover states.) */

  /* ── 10. CONFIRM DIALOGS (data-confirm attribute) ──────────────────────── */
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-confirm]');
    if (!el) return;
    const msg = el.dataset.confirm || 'Are you sure?';
    if (!confirm(msg)) e.preventDefault();
  });

  /* ── 11. MOBILE NAV — close on outside click ──────────────────────────── */
  document.addEventListener('click', function (e) {
    const toggler = document.querySelector('.navbar-toggler');
    const collapse = document.querySelector('.navbar-collapse.show');
    if (collapse && toggler && !collapse.contains(e.target) && !toggler.contains(e.target)) {
      toggler.click();
    }
  });

  /* ── 12. LAZY-LOAD IMAGES ─────────────────────────────────────────────── */
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

  /* ── 13. COPY-TO-CLIPBOARD (data-copy) ────────────────────────────────── */
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

  /* ── 14. KEYBOARD SHORTCUTS ───────────────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    // Escape closes active Bootstrap Modals
    if (e.key === 'Escape') {
      const modal = document.querySelector('.modal.show');
      if (modal && window.bootstrap && bootstrap.Modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
      }
    }
  });

  /* ── 15. LOADING OVERLAY ──────────────────────────────────────────────── */
  window.showLoading = function (message) {
    message = message || 'Loading...';
    let overlay = document.getElementById('sp-loading-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'sp-loading-overlay';
      overlay.style.cssText = [
        'position:fixed', 'inset:0', 'background:rgba(0,10,46,0.45)',
        'display:flex', 'align-items:center', 'justify-content:center', 'z-index:99999',
        'opacity:0', 'transition:opacity .25s ease',
      ].join(';');

      overlay.innerHTML = `
        <div style="background:var(--bg-card,#fff);padding:2.5rem;border-radius:16px;text-align:center;box-shadow:var(--shadow-lg);max-width:320px;width:90%">
          <div class="loading" style="width:3rem;height:3rem;border-width:4px;margin:0 auto 1.25rem"></div>
          <p id="sp-loading-text" style="margin:0;color:var(--ink-700,#334155);font-weight:600;font-size:15px"></p>
        </div>
      `;
      overlay.querySelector('#sp-loading-text').textContent = message;
      document.body.appendChild(overlay);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => overlay.style.opacity = '1');
      });
    } else {
      document.getElementById('sp-loading-text').textContent = message;
      overlay.style.display = 'flex';
      requestAnimationFrame(() => overlay.style.opacity = '1');
    }
  };

  window.hideLoading = function () {
    const overlay = document.getElementById('sp-loading-overlay');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.style.display = 'none', 260);
    }
  };

  /* ── 16. FORM ENHANCEMENT (VALIDATION STATES) ────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form.needs-validation').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
        }
        form.classList.add('was-validated');
      }, false);
    });

    // Realtime feedback for required inputs (dirty-aware)
    document.querySelectorAll('input[required], select[required], textarea[required]').forEach(function (input) {
      input.addEventListener('input', function () {
        input.classList.add('is-dirty');
      });
      
      input.addEventListener('blur', function () {
        // Only show validation feedback if the user has actually interacted with the field (is-dirty) or if it is not empty
        if (input.value.trim() !== '' || input.classList.contains('is-dirty')) {
          if (input.validity.valid) {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
          } else {
            input.classList.remove('is-valid');
            input.classList.add('is-invalid');
          }
        }
      });
    });
  });

  /* ── 17. NOTIFICATION BADGE UNREAD COUNT ───────────────────────────────── */
  window.updateNotificationBadge = async function () {
    try {
      const resp = await fetch('/notifications/api/unread-count');
      if (!resp.ok) return;
      const data = await resp.json();
      const badge = document.getElementById('notif-badge');
      if (badge) {
        badge.textContent = data.unread_count || '';
        badge.style.display = data.unread_count > 0 ? 'inline-flex' : 'none';
      }
    } catch (e) {
      // Silently fail
    }
  };

  // Run on load
  document.addEventListener('DOMContentLoaded', function () {
    window.updateNotificationBadge();
    // Poll for notifications every 3 minutes if logged in
    if (document.getElementById('notif-badge')) {
      setInterval(window.updateNotificationBadge, 180000);
    }

    // ── 18. PHONE NUMBER NUMERIC INPUT CONSTRAINT ──
    const filterPhoneInput = function(e) {
      const val = e.target.value;
      const cleanVal = val.replace(/[^0-9]/g, '');
      if (val !== cleanVal) {
        e.target.value = cleanVal;
      }
    };

    // Attach to any inputs currently present
    document.querySelectorAll('input[type="tel"]').forEach(function(input) {
      input.addEventListener('input', filterPhoneInput);
    });

    // Delegate listener to handle dynamically appended inputs
    document.addEventListener('input', function(e) {
      if (e.target && e.target.tagName === 'INPUT' && e.target.type === 'tel') {
        filterPhoneInput(e);
      }
    });

  });
})();
