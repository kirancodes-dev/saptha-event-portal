"""
tests/test_merged_subsystems.py — UPG-14: one notification system (a
notification made with create_notification shows in the feed the dashboards
load), no Stripe, no old scheduler module, and the mock-data matchmaker hidden
unless FEATURE_MATCHMAKER is switched on.
"""
import os
import re
import subprocess
import sys

import pytest

from routes_notifications_v2 import create_notification
from tests.test_integration_flow import _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def student(real_app):
    flask_app, db = real_app
    email = f"{_unique('notif')}@test.edu"
    _user(db, email, 'Student')
    return flask_app, db, email, _login(flask_app, email, 'Student')


def test_a_created_notification_appears_in_the_dashboard_feed(student):
    flask_app, db, email, client = student
    other = f"{_unique('someone')}@test.edu"
    create_notification(db, user_email=email, notif_type='event_reminder', title='Hackathon tomorrow',
                        message='Bring your ID card', link='/participant/my_events')
    create_notification(db, user_email=other, notif_type='event_reminder', title='Not yours', message='x')

    feed = client.get('/notifications/feed')
    assert feed.status_code == 200
    text = feed.get_data(as_text=True)
    assert 'Hackathon tomorrow' in text and 'Bring your ID card' in text
    assert 'Not yours' not in text
    # The dashboard's bell loads that feed
    assert '/static/js/notifications.js' in client.get('/participant/dashboard').get_data(as_text=True)
    with open(os.path.join(ROOT, 'static', 'js', 'notifications.js')) as f:
        assert "fetch('/notifications/feed'" in f.read()


def test_stripe_checkout_is_gone(real_app):
    flask_app, _ = real_app
    client = flask_app.test_client()
    assert client.get('/payment/stripe/create_session').status_code == 404
    assert client.post('/payment/stripe/create_session').status_code == 404


def test_nothing_imports_the_old_scheduler_and_the_duplicates_are_gone():
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for gone in ('scheduler.py', 'tests.py', 'routes_notifications.py', 'routes_payment_stripe.py'):
        assert gone not in tracked, gone
    old_import = re.compile(r'^\s*(import\s+scheduler\b(?!_)|from\s+scheduler\s+import)', re.M)
    for path in (p for p in tracked if p.endswith('.py')):
        with open(os.path.join(ROOT, path), encoding='utf-8', errors='ignore') as f:
            assert not old_import.search(f.read()), path


def test_the_matchmaker_is_404_unless_the_flag_is_on(student):
    flask_app, _, _, client = student
    assert flask_app.config.get('FEATURE_MATCHMAKER') is False
    assert client.get('/participant/matchmaker/').status_code == 404
    assert client.post('/participant/matchmaker/api/match', json={}).status_code == 404
    flask_app.config['FEATURE_MATCHMAKER'] = True
    try:
        assert client.get('/participant/matchmaker/').status_code == 200
    finally:
        flask_app.config['FEATURE_MATCHMAKER'] = False


@pytest.mark.parametrize('value, on', [('true', True), ('1', True), ('', False), ('false', False)])
def test_the_matchmaker_flag_comes_from_the_environment(value, on):
    env = dict(os.environ, FEATURE_MATCHMAKER=value)
    out = subprocess.run([sys.executable, '-c', 'from config import Config; print(Config.FEATURE_MATCHMAKER)'],
                         cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(on)
