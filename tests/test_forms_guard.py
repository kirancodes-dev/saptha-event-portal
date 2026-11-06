"""
tests/test_forms_guard.py — UPG-26: every page with a form loads the submit
guard (static/js/forms.js, from the shared document); every visible input,
select and textarea on the key form pages has a label or aria-label; the same
registration posted twice, one after the other or at the same instant, makes
one registration; the payment button stays disabled from the first click
until the payment's result arrives (headless Chromium, Razorpay's checkout.js
and the order/verify calls replaced by stand-ins).
"""
import threading

from tests.test_integration_flow import _unique
from tests.test_paid_events import paid, rzp  # noqa: F401  (fixtures)
from tests.test_shared_layout import _chain, _key_pages, _rendered_templates, roles  # noqa: F401  (fixture)

GUARD = '/static/js/forms.js'


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_shared_document_loads_the_guard_for_every_page():
    import os
    from tests.test_shared_layout import TEMPLATES
    with open(os.path.join(TEMPLATES, 'layouts', 'document.html'), encoding='utf-8') as f:
        assert f'<script src="{GUARD}"></script>' in f.read()
    with_forms = []
    for name in _rendered_templates():
        with open(os.path.join(TEMPLATES, name), encoding='utf-8') as f:
            if '<form' in f.read():
                with_forms.append(name)
    assert len(with_forms) > 30
    assert [n for n in with_forms if 'layouts/document.html' not in _chain(n)] == []


def test_each_key_page_with_a_form_loads_the_guard(roles):  # noqa: F811
    missing, forms = [], 0
    for who, paths in _key_pages(roles).items():
        for path in paths:
            html = roles['clients'][who].get(path).get_data(as_text=True)
            if '<form' in html:
                forms += 1
                if f'src="{GUARD}"' not in html:
                    missing.append((who, path))
    assert forms >= 10 and missing == []


# ── Criterion 2 ─────────────────────────────────────────────────────────────

UNLABELLED = """() => {
  const visible = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return [...document.querySelectorAll('input, select, textarea')]
    .filter(el => !['hidden', 'submit', 'button', 'reset', 'image'].includes((el.type || '').toLowerCase()))
    .filter(visible)
    .filter(el => !(el.labels && el.labels.length) && !el.getAttribute('aria-label')
                  && !el.getAttribute('aria-labelledby'))
    .map(el => (el.name || el.id || el.type) + ' ' + el.outerHTML.slice(0, 80));
}"""


def _serving(html, bootstrap):
    from tests.headless import _serve_static

    def handle(route):
        if route.request.resource_type == 'document':
            return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html'})
        if 'bootstrap@5.3.3/dist/css' in route.request.url:
            return route.fulfill(status=200, body=bootstrap, content_type='text/css')
        return _serve_static(route)
    return handle


def test_every_visible_field_on_the_key_pages_has_a_label(roles):  # noqa: F811
    from tests.headless import ORIGIN, chromium
    from tests.test_shared_layout import BOOTSTRAP
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()
    extra = {'anonymous': ['/forgot_password', '/register'], 'spoc': [f"/spoc/edit_event/{roles['event_id']}"],
             'admin': ['/admin/send_email']}
    p, browser = chromium()
    problems, fields_pages = [], 0
    try:
        for who, paths in _key_pages(roles).items():
            for path in paths + extra.get(who, []):
                resp = roles['clients'][who].get(path)
                if resp.status_code != 200:
                    problems.append((who, path, resp.status_code))
                    continue
                html = resp.get_data(as_text=True)
                page = browser.new_page()

                page.route('**/*', _serving(html, bootstrap))
                page.goto(ORIGIN + path, wait_until='load')
                page.wait_for_timeout(200)
                if page.evaluate("() => document.querySelectorAll('input, select, textarea').length"):
                    fields_pages += 1
                found = page.evaluate(UNLABELLED)
                page.close()
                if found:
                    problems.append((who, path, found[:4]))
    finally:
        browser.close()
        p.stop()
    assert fields_pages >= 12
    assert problems == [], '\n'.join(map(str, problems))


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def _form(email, key):
    return {'privacy_consent': 'yes', 'full_name': 'Twice Sent', 'email': email, 'phone': '9876543210',
            'usn': '1SN20CS555', 'submission_id': key}


def _free_event(d):
    from tests.test_integration_flow import _create_event
    event_id = _create_event(d['owner'], d['db'], _unique('Free Talk'), '2030-07-01', team=False)
    d['db'].collection('events').document(event_id).update({'status': 'registration_open'})
    return event_id


def _regs_for(d, event_id, email):
    return [r for r in (x.to_dict() for x in d['db'].collection('registrations').where('event_id', '==', event_id).stream())
            if r.get('lead_email') == email]


def test_the_same_registration_sent_twice_registers_once(paid):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    email, key = f"{_unique('twice')}@test.edu", _unique('sub')
    client = d['app'].test_client()
    first = client.post(f'/forms/submit/{event_id}', data=_form(email, key))
    second = client.post(f'/forms/submit/{event_id}', data=_form(email, key), follow_redirects=True)
    assert first.status_code == 302 and second.status_code == 200
    # One after the other, the duplicate check answers first; at the same instant
    # (below) it's the submission key that keeps it to one
    said = second.get_data(as_text=True)
    assert 'already registered for this event' in said or 'it was sent twice, and we registered it once' in said
    assert len(_regs_for(d, event_id, email)) == 1


def test_two_copies_sent_at_the_same_instant_register_once(paid):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    email, key = f"{_unique('race')}@test.edu", _unique('sub')
    start, statuses = threading.Barrier(2), []

    def send():
        client = d['app'].test_client()
        start.wait()
        statuses.append(client.post(f'/forms/submit/{event_id}', data=_form(email, key)).status_code)
    threads = [threading.Thread(target=send) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert statuses == [302, 302]
    assert len(_regs_for(d, event_id, email)) == 1


# ── Criterion 4 ─────────────────────────────────────────────────────────────

FAKE_RAZORPAY = """
window.Razorpay = function (options) {
  window.__rzp = options; window.__rzpOn = {}; window.__opened = (window.__opened || 0);
  this.on = function (name, fn) { window.__rzpOn[name] = fn; };
  this.open = function () { window.__opened += 1; };
};
"""


def test_the_payment_button_stays_disabled_until_the_result_arrives(paid):  # noqa: F811
    from tests.headless import ORIGIN, _serve_static, chromium
    d = paid
    client = d['app'].test_client()
    email = f"{_unique('payguard')}@test.edu"
    client.post(f"/forms/submit/{d['event_id']}", data={'privacy_consent': 'yes', 'full_name': 'Pay Guard',
                                                        'email': email, 'phone': '9876543210', 'usn': '1SN20CS556'})
    path = f"/payment/checkout/{d['event_id']}"
    html = client.get(path).get_data(as_text=True)
    assert 'id="pay-btn"' in html
    calls = {'create_order': 0, 'verify': 0}

    def handle(route):
        url = route.request.url
        if route.request.resource_type == 'document':
            return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html'})
        if 'checkout.razorpay.com' in url:
            return route.fulfill(status=200, body=FAKE_RAZORPAY, content_type='application/javascript')
        if url.endswith('/payment/create_order'):
            calls['create_order'] += 1
            return route.fulfill(status=200, content_type='application/json',
                                 body='{"key": "rzp_test_x", "amount": 25000, "order_id": "order_fake1", '
                                      '"name": "Pay Guard", "email": "pg@test.edu"}')
        if url.endswith('/payment/verify'):
            calls['verify'] += 1
            return route.fulfill(status=200, content_type='application/json',
                                 body='{"pending": true, "message": "Payment received; confirming."}')
        return _serve_static(route)

    p, browser = chromium()
    try:
        page = browser.new_page()
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        disabled = "() => document.getElementById('pay-btn').disabled"

        page.click('#pay-btn')
        page.wait_for_function('() => window.__opened === 1')
        assert page.evaluate(disabled) is True
        page.evaluate("() => document.getElementById('pay-btn').click()")      # a second click does nothing
        page.wait_for_timeout(300)
        assert calls['create_order'] == 1 and page.evaluate('() => window.__opened') == 1

        page.evaluate('() => window.__rzp.modal.ondismiss()')                   # result: cancelled
        assert page.evaluate(disabled) is False

        page.click('#pay-btn')                                                   # pay again, and succeed
        page.wait_for_function('() => window.__opened === 2')
        page.evaluate("() => window.__rzp.handler({razorpay_order_id: 'order_fake1', "
                      "razorpay_payment_id: 'pay_fake1', razorpay_signature: 'sig'})")
        page.wait_for_function("() => document.getElementById('pay-btn').textContent.includes('Payment received')")
        assert page.evaluate(disabled) is True and calls == {'create_order': 2, 'verify': 1}
    finally:
        browser.close()
        p.stop()
