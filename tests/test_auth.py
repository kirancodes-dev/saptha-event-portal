"""
tests/test_auth.py — Auth route smoke tests
"""


def test_login_page_loads(client):
    resp = client.get('/login')
    assert resp.status_code == 200


def test_home_redirects_logged_in_student(student_session):
    resp = student_session.get('/')
    # Logged-in student should be redirected to participant dashboard
    assert resp.status_code in (301, 302)
    assert b'participant' in resp.headers.get('Location', '').encode()


def test_home_loads_for_anonymous(client, mock_db):
    mock_db.collection.return_value \
           .where.return_value \
           .stream.return_value = iter([])
    resp = client.get('/')
    assert resp.status_code == 200


def test_login_post_missing_fields(client):
    resp = client.post('/login', data={}, follow_redirects=False)
    # Missing credentials — should stay on login or redirect back
    assert resp.status_code in (200, 302, 400)


def test_protected_route_requires_login(client):
    resp = client.get('/participant/dashboard', follow_redirects=False)
    assert resp.status_code in (302, 401)
