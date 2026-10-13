/* Moved unchanged from an inline <script> in templates/includes/csrf_fetch.html so the CSP
   needs no inline script (UPG-25). */
    // Auto-attach the CSRF token to same-origin mutating fetch() requests.
    (function () {
        var meta = document.querySelector('meta[name="csrf-token"]');
        var token = meta ? meta.getAttribute('content') : '';
        if (!token || !window.fetch) return;
        var origFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            init = init || {};
            var method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
            if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(method) === -1) {
                return origFetch(input, init);
            }
            var url = typeof input === 'string' ? input : (input && input.url) || '';
            try {
                var u = new URL(url, window.location.origin);
                if (u.origin !== window.location.origin) return origFetch(input, init);
            } catch (_) {}
            var headers = new Headers(init.headers || {});
            if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
            init.headers = headers;
            if (!init.credentials) init.credentials = 'same-origin';
            return origFetch(input, init);
        };
    })();
