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


# ── UPG-104 ─────────────────────────────────────────────────────────────────

def _style_block():
    import re
    with open('templates/participant/dashboard.html', encoding='utf-8') as fh:
        return re.search(r'<style>(.*?)</style>', fh.read(), re.S).group(1)


def test_the_dashboard_style_block_is_balanced():
    css = _style_block()
    assert css.count('{') == css.count('}')
    assert '.portal-widgets-grid { display: grid' in css   # the grid isn't inside a media query


def _registered(student, title, date, category='Technical', reg_status='Confirmed'):
    import datetime
    from tests.test_integration_flow import _create_event
    db = student['db']
    if 'spoc' not in student:
        spoc = f"{_unique('dashspoc')}@test.edu"
        _user(db, spoc, 'ClubSPOC')
        student['spoc'] = _login(student['app'], spoc, 'ClubSPOC')
    event_id = _create_event(student['spoc'], db, title, date, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open', 'category': category})
    db.collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_email': student['email'], 'lead_name': 'Dash Board',
        'status': reg_status, 'payment_status': 'Free', 'attendance': 'Pending',
        'registered_at': datetime.datetime.now().isoformat()})
    return event_id


def _sections(page):
    active = page[page.index('id="tickets-section"'):]
    past = active[active.index('id="past"'):] if 'id="past"' in active else ''
    active = active[:active.index('id="past"')] if past else active
    return active, past


def test_only_future_not_cancelled_registrations_are_upcoming(student):
    import datetime
    day = lambda n: (datetime.date.today() + datetime.timedelta(days=n)).isoformat()   # noqa: E731
    future, ended, cancelled = (_unique('Future Fest'), _unique('Ended Expo'), _unique('Cancelled Camp'))
    _registered(student, future, day(5))
    _registered(student, ended, day(-3))
    _registered(student, cancelled, day(7), reg_status='Cancelled')
    active, past = _sections(student['client'].get('/participant/dashboard').get_data(as_text=True))
    assert future in active
    assert ended not in active and ended in past
    assert cancelled not in active and cancelled in past and 'Cancelled</span>' in past


def test_the_tabs_come_from_the_students_own_registrations(student):
    import datetime
    import re
    day = lambda n: (datetime.date.today() + datetime.timedelta(days=n)).isoformat()   # noqa: E731
    _registered(student, _unique('Tech Talk'), day(3), 'Technical')
    _registered(student, _unique('Tech Lab'), day(4), 'Technical')
    _registered(student, _unique('Budget Bootcamp'), day(6), 'Management')
    page = student['client'].get('/participant/dashboard').get_data(as_text=True)
    tabs = dict(re.findall(r'data-filter="([^"]+)">([^<]+)<span class="seg__count">', page))
    counts = dict(re.findall(r'data-filter="([^"]+)">[^<]+<span class="seg__count">(\d+)</span>', page))
    assert tabs == {'all': 'All', 'active': 'Upcoming', 'past': 'Past',
                    'cat-technical': 'Technical', 'cat-management': 'Management'}
    assert counts == {'all': '3', 'active': '3', 'past': '0', 'cat-technical': '2', 'cat-management': '1'}
    assert page.count('data-category="cat-management"') == 1 and 'id="tab-empty"' in page
