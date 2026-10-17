"""
tests/test_announcement_escaping.py — UPG-77: what a Super Admin types into an
announcement email is sent as text, never as HTML, with its line breaks kept.
"""
from tests.test_integration_flow import PASSWORD, _unique, _user


def test_markup_in_an_announcement_arrives_as_text(real_app, monkeypatch):
    import utils_email
    flask_app, db = real_app
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append((to, subject, html)) or True)
    judge = f"{_unique('ann-judge')}@test.edu"
    _user(db, judge, 'Judge')
    admin = f"{_unique('ann-admin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})

    resp = client.post('/admin/send_email', data={
        'audience': 'role_filter', 'role_filter': 'Judge', 'channel': 'email',
        'subject': 'Rooms <i>changed</i>', 'message': 'Hall <b>B</b> & lab\nSecond line <script>x</script>'})
    assert resp.status_code == 200
    [(_, subject, html)] = [m for m in sent if m[0] == judge]
    assert '<b>B</b>' not in html and '<script>' not in html and '<i>changed</i>' not in html
    assert 'Hall &lt;b&gt;B&lt;/b&gt; &amp; lab\nSecond line &lt;script&gt;x&lt;/script&gt;' in html   # newline kept
    assert 'white-space:pre-line' in html and 'Rooms &lt;i&gt;changed&lt;/i&gt;' in html
