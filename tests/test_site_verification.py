"""
tests/test_site_verification.py — UPG-107: Google Search Console's ownership
file is served at the site root with its exact contents.
"""


def test_the_google_verification_file_is_served_at_the_root(real_app):
    flask_app, _ = real_app
    resp = flask_app.test_client().get('/google8e55d49885709546.html')
    assert resp.status_code == 200 and resp.mimetype == 'text/html'
    assert resp.get_data(as_text=True) == 'google-site-verification: google8e55d49885709546.html'
