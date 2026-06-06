/**
 * pwa.js — Service Worker registration & mobile enhancements
 * ============================================================
 */

(function () {
  'use strict';

  var deferredPrompt = null;



  // 2. OFFLINE DETECTION
  function updateOnlineStatus() {
    var banner = document.getElementById('offlineBanner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'offlineBanner';
      banner.className = 'offline-banner';
      banner.innerHTML = '<i class="fas fa-plane-slash"></i> You are currently offline. Using cached event database.';
      document.body.appendChild(banner);
    }
    
    if (navigator.onLine) {
      banner.style.display = 'none';
    } else {
      banner.style.display = 'flex';
    }
  }

  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  document.addEventListener('DOMContentLoaded', updateOnlineStatus);



  // 4. WEB SHARE API INTEGRATION
  window.shareEvent = function (title, text, url) {
    if (navigator.share) {
      navigator.share({
        title: title,
        text: text,
        url: url || window.location.href
      })
      .then(function() { console.log('[PWA] Shared successfully'); })
      .catch(function(err) { console.error('[PWA] Share error:', err); });
    } else {
      // Fallback: Copy to Clipboard
      navigator.clipboard.writeText(url || window.location.href)
        .then(function() {
          showToast('Link Copied', 'Event URL copied to clipboard!', 'success');
        });
    }
  };

  // 5. TOAST HELPER
  function showToast(title, body, type, action) {
    var container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.position = 'fixed';
      container.style.bottom = '80px';
      container.style.right = '20px';
      container.style.zIndex = '9999';
      document.body.appendChild(container);
    }

    var toast = document.createElement('div');
    toast.className = 'toast show bg-dark text-white border-secondary p-3 mb-2 rounded-3';
    toast.style.minWidth = '280px';
    toast.style.boxShadow = '0 8px 30px rgba(0,0,0,0.3)';
    
    var head = '<div class="d-flex justify-content-between align-items-center mb-1">' +
               '<strong class="text-warning">' + title + '</strong>' +
               '<button type="button" class="btn-close btn-close-white small" onclick="this.parentElement.parentElement.remove()"></button>' +
               '</div>';
    var textBody = '<div>' + body + '</div>';
    
    if (action) {
      textBody += '<button class="btn btn-sm btn-warning mt-2 w-100" id="toastActionBtn">Execute</button>';
    }

    toast.innerHTML = head + textBody;
    container.appendChild(toast);
    
    if (action) {
      var actBtn = toast.querySelector('#toastActionBtn');
      actBtn.onclick = function() {
        action();
        toast.remove();
      };
    } else {
      setTimeout(function () {
        toast.remove();
      }, 5000);
    }
  }

})();
