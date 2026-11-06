"""
tests/test_confetti_csp.py — UPG-70: the certificate verification pages' confetti
runs without a web worker, so the app's CSP (which refuses blob: workers)
logs no violation. The CDN library is replaced offline by a stand-in that, like
canvas-confetti, starts a blob: worker unless asked not to.
"""
import pytest

from tests.headless import page_problems

STAND_IN = """
(function () {
  function cannon(opts) {
    if (!opts || opts.useWorker !== false) {
      new Worker(URL.createObjectURL(new Blob(['onmessage=function(){}'], {type: 'application/javascript'})));
    }
    return function () { return null; };
  }
  var fire = null;
  window.confetti = function () { if (!fire) fire = cannon({ useWorker: true }); return fire.apply(null, arguments); };
  window.confetti.create = function (canvas, opts) { return cannon(opts || {}); };
})();
"""


@pytest.mark.parametrize('script', ['public__verify_success.js', 'public__verify_certificate.js'])
def test_the_verification_confetti_needs_no_worker_under_the_apps_csp(real_app, script):
    flask_app, _ = real_app
    csp = flask_app.test_client().get('/').headers['Content-Security-Policy']
    html = ('<!doctype html><html><head>'
            '<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>'
            f'<script src="/static/js/pages/{script}"></script></head><body>Verified</body></html>')
    errors, violations, _ = page_problems(html, '/verify/sample', csp=csp, wait_ms=900,
                                          stand_ins={'canvas-confetti': (STAND_IN, 'application/javascript')})
    assert violations == [] and errors == []
