/**
 * api_explorer.js — Interactive client-side API Explorer logic
 * ============================================================
 */

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    bindCodeTabs();
    bindAPIExecution();
    bindSidebarNavigation();
    bindCopyButtons();
  });

  // 1. TAB SWITCHING FOR CODE SAMPLES
  function bindCodeTabs() {
    document.addEventListener('click', function (e) {
      var tab = e.target.closest('.code-tab');
      if (!tab) return;

      var parent = tab.closest('.code-block-wrap');
      if (!parent) return;

      var lang = tab.getAttribute('data-lang');
      
      // Toggle active tab header
      parent.querySelectorAll('.code-tab').forEach(function (btn) {
        btn.classList.remove('active');
      });
      tab.classList.add('active');

      // Toggle displayed snippet
      parent.querySelectorAll('.code-snippet').forEach(function (pre) {
        if (pre.getAttribute('data-lang') === lang) {
          pre.classList.remove('d-none');
        } else {
          pre.classList.add('d-none');
        }
      });
    });
  }

  // 2. RUNTIME API EXECUTION (TRY IT OUT)
  function bindAPIExecution() {
    document.addEventListener('submit', function (e) {
      var form = e.target.closest('.try-api-form');
      if (!form) return;

      e.preventDefault();

      var endpointId = form.getAttribute('data-endpoint-id');
      var method = form.getAttribute('data-method');
      var path = form.getAttribute('data-path');
      var responsePre = document.getElementById('response-' + endpointId);

      if (!responsePre) return;

      responsePre.textContent = 'Sending request...';
      responsePre.style.color = '#8b949e';

      // Gather input params
      var headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
      };

      // Add auth token if provided
      var tokenInput = document.getElementById('api-global-token');
      if (tokenInput && tokenInput.value.trim()) {
        headers['Authorization'] = 'Bearer ' + tokenInput.value.trim();
      }

      var payload = {};
      var queryParams = [];
      var pathVariables = {};

      var inputs = form.querySelectorAll('input, select, textarea');
      inputs.forEach(function (input) {
        var name = input.getAttribute('name');
        if (!name) return;

        var type = input.getAttribute('data-param-type');
        var val = input.value;

        if (type === 'path') {
          pathVariables[name] = val;
        } else if (type === 'query') {
          if (val) queryParams.push(encodeURIComponent(name) + '=' + encodeURIComponent(val));
        } else {
          // body param
          if (input.type === 'number') {
            payload[name] = val ? parseFloat(val) : null;
          } else {
            payload[name] = val;
          }
        }
      });

      // Construct final URL path
      var finalPath = path;
      Object.keys(pathVariables).forEach(function (key) {
        finalPath = finalPath.replace('{' + key + '}', pathVariables[key]).replace('<' + key + '>', pathVariables[key]).replace('<id>', pathVariables[key]).replace('<email>', pathVariables[key]);
      });

      if (queryParams.length > 0) {
        finalPath += '?' + queryParams.join('&');
      }

      var fetchOptions = {
        method: method,
        headers: headers,
        credentials: 'same-origin'
      };

      if (method !== 'GET' && Object.keys(payload).length > 0) {
        fetchOptions.body = JSON.stringify(payload);
      }

      fetch(finalPath, fetchOptions)
        .then(function (res) {
          var statusText = 'HTTP ' + res.status + ' ' + res.statusText;
          responsePre.setAttribute('data-status', res.status);
          
          if (res.status >= 200 && res.status < 300) {
            responsePre.style.color = '#79c0ff'; // Blue green highlight
          } else {
            responsePre.style.color = '#ff7b72'; // Red warning
          }

          return res.json().then(function (json) {
            responsePre.textContent = statusText + '\n\n' + JSON.stringify(json, null, 2);
          }).catch(function() {
            return res.text().then(function (text) {
              responsePre.textContent = statusText + '\n\n' + text;
            });
          });
        })
        .catch(function (err) {
          responsePre.style.color = '#ff7b72';
          responsePre.textContent = 'Network Error:\n\n' + err.message;
        });
    });
  }

  // 3. SIDEBAR HIGHLIGHTING ON SCROLL
  function bindSidebarNavigation() {
    var sections = document.querySelectorAll('.endpoint-section');
    var menuLinks = document.querySelectorAll('.dev-menu-item');

    if (sections.length === 0 || menuLinks.length === 0) return;

    window.addEventListener('scroll', function () {
      var current = '';
      var scrollPos = window.scrollY || document.documentElement.scrollTop;

      sections.forEach(function (section) {
        var top = section.offsetTop - 120;
        if (scrollPos >= top) {
          current = section.getAttribute('id');
        }
      });

      if (current) {
        menuLinks.forEach(function (link) {
          link.classList.remove('active');
          if (link.getAttribute('data-target') === current) {
            link.classList.add('active');
          }
        });
      }
    });
  }

  // 4. COPY CODE SNIPPETS
  function bindCopyButtons() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.copy-btn');
      if (!btn) return;

      var parent = btn.closest('.code-block-wrap');
      if (!parent) return;

      // Find currently visible snippet block
      var visiblePre = parent.querySelector('.code-snippet:not(.d-none) code');
      if (!visiblePre) return;

      var text = visiblePre.textContent;
      navigator.clipboard.writeText(text).then(function () {
        var origHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check text-success"></i>';
        setTimeout(function () {
          btn.innerHTML = origHtml;
        }, 1500);
      });
    });
  }

})();
