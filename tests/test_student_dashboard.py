"""
tests/test_student_dashboard.py — the student dashboard on the real database
layer: the referral section is hidden unless switched on (UPG-105).
"""
import pytest

from tests.test_integration_flow import _login, _unique, _user


@pytest.fixture
def student(real_app):
    flask_app, db = real_app
    email = f"{_unique('dash')}@test.edu"
    _user(db, email, 'Student')
    return {'app': flask_app, 'db': db, 'email': email, 'client': _login(flask_app, email, 'Student')}


# ── UPG-105 ─────────────────────────────────────────────────────────────────

def test_the_referral_section_is_hidden_unless_switched_on(student):
    page = student['client'].get('/participant/dashboard').get_data(as_text=True)
    assert 'Refer students, earn rewards' not in page and '/participant/referrals/api/stats' not in page

    student['app'].config['REFERRALS_ENABLED'] = True
    try:
        page = student['client'].get('/participant/dashboard').get_data(as_text=True)
        assert 'Refer students, earn rewards' in page and '/participant/referrals/api/stats' in page
    finally:
        student['app'].config['REFERRALS_ENABLED'] = False
