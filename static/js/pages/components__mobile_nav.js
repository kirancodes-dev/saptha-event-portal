/* Moved unchanged from an inline <script> in templates/components/mobile_nav.html so the CSP
   needs no inline script (UPG-25). */
(function() {
  var isIOS     = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  var isAndroid = /Android/.test(navigator.userAgent);
  var isChrome  = /Chrome/.test(navigator.userAgent) && !/Edg/.test(navigator.userAgent);
  var isSafari  = /Safari/.test(navigator.userAgent) && !isChrome;
  var isInstalled = window.matchMedia('(display-mode: standalone)').matches
                 || window.navigator.standalone === true
                 || localStorage.getItem('pwa_installed') === '1';

  // ── Hide the Install nav button if already installed ────
  if (isInstalled && !window.pwaUpdateAvailable) {
    var btn = document.getElementById('mn-install-btn');
    if (btn) btn.style.display = 'none';
  }

  // ── Modal open / close ────────────────────────────────────
  window.showPwaInstallModal = function() {
    var modal  = document.getElementById('pwaInstallModal');
    var sheet  = document.getElementById('pwaModalSheet');
    var androidSection = document.getElementById('pwaAndroidSection');
    var iosSection     = document.getElementById('pwaIosSection');
    var chromeFallback = document.getElementById('pwaChromeFallback');

    // Decide which instructions to show
    if (isIOS || isSafari) {
      // iOS always needs manual steps
      androidSection.style.display = 'none';
      iosSection.style.display     = 'block';
    } else if (window.__pwaPrompt) {
      // Android Chrome with native prompt ready
      androidSection.style.display = 'block';
      iosSection.style.display     = 'none';
    } else {
      // No native prompt (might be late, might be Chrome with engagement not met)
      androidSection.style.display = 'none';
      iosSection.style.display     = 'block';
      if (isAndroid) chromeFallback.style.display = 'block';
    }

    modal.style.display = 'flex';
    // Animate in
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        sheet.style.transform = 'translateY(0)';
      });
    });
  };

  window.closePwaModal = function() {
    var sheet = document.getElementById('pwaModalSheet');
    var modal = document.getElementById('pwaInstallModal');
    sheet.style.transform = 'translateY(100%)';
    setTimeout(function() { modal.style.display = 'none'; }, 350);
  };

  window.triggerNativeInstall = async function() {
    if (!window.__pwaPrompt) {
      // Prompt gone — fall back to manual instructions
      document.getElementById('pwaAndroidSection').style.display = 'none';
      document.getElementById('pwaIosSection').style.display = 'block';
      document.getElementById('pwaChromeFallback').style.display = 'block';
      return;
    }
    window.__pwaPrompt.prompt();
    var result = await window.__pwaPrompt.userChoice;
    window.__pwaPrompt = null;
    window.closePwaModal();
    if (result.outcome === 'accepted') {
      localStorage.setItem('pwa_banner_dismissed', '1');
    }
  };

  // ── Capture the beforeinstallprompt event globally ────────
  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    window.__pwaPrompt = e;
    // Also update the Install button if modal is open
    var androidSection = document.getElementById('pwaAndroidSection');
    var iosSection     = document.getElementById('pwaIosSection');
    if (androidSection && iosSection) {
      androidSection.style.display = 'block';
      iosSection.style.display     = 'none';
    }
  });

  // ── Highlight active bottom nav item based on current URL path ──
  var path = window.location.pathname;
  var hash = window.location.hash;
  var items = document.querySelectorAll('.mobile-nav-bar .mobile-nav-item');
  items.forEach(function(item) {
    item.classList.remove('active');
    var href = item.getAttribute('href');
    if (href) {
      if (href === '/' && path === '/' && !hash) {
        item.classList.add('active');
      } else if (href === '/#events' && hash === '#events') {
        item.classList.add('active');
      } else if (href !== '/' && href !== '/#events') {
        var baseHref = href.split('?')[0].split('#')[0];
        if (path === baseHref || path.startsWith(baseHref + '/')) {
          item.classList.add('active');
        }
      }
    }
  });

  // ── Auto-show modal once after 3 page visits ──────────────
  if (!isInstalled && localStorage.getItem('pwa_banner_dismissed') !== '1') {
    var visits = parseInt(localStorage.getItem('pwa_visit_count') || '0', 10) + 1;
    localStorage.setItem('pwa_visit_count', String(visits));
    if (visits === 3) {
      // Show on 3rd visit to avoid being annoying on first load
      setTimeout(function() { window.showPwaInstallModal(); }, 3000);
    }
  }
})();
