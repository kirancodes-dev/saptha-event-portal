"""
tests/test_team_member_notices.py — UPG-48 on the real database layer (Brevo's
API mocked, network blocked): every member of a team, not only the lead, gets
the confirmation (when listed and when joining by code), the day-before ticket
through the cron endpoint, and the change and cancellation notices, each once,
whatever the case of their email.
"""
import pytest

from tests import test_notices
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_notices import CRON, _day, _to

site = test_notices.site
brevo = test_notices.brevo
offline = test_notices.offline


@pytest.fixture(autouse=True)
def _team_members_notified(monkeypatch):
    """Since UPG-152 only the lead is emailed unless NOTIFY_TEAM_MEMBERS is on;
    these tests are about what members get when it is."""
    import app as app_module
    monkeypatch.setitem(app_module.app.config, 'NOTIFY_TEAM_MEMBERS', True)


def _team(d, date):
    title = _unique('Team Night')
    event_id = _create_event(d['owner'], d['db'], title, date, team=True)
    d['db'].collection('events').document(event_id).update({'status': 'registration_open', 'venue': 'Hall A'})
    lead = f"{_unique('lead')}@test.edu"
    mates = [f"{_unique('mate1')}@test.edu", f"{_unique('MATE2')}@test.edu".upper()]
    form = {'privacy_consent': 'yes', 'full_name': 'Lee Lead', 'email': lead, 'phone': '9876543210',
            'usn': '1SN22CS100', 'team_name': 'Byte Force'}
    for i, email in enumerate(mates, start=1):
        form.update({f'member_{i}_name': f'Mate {i}', f'member_{i}_email': email, f'member_{i}_usn': f'1SN22CS10{i}'})
    assert d['app'].test_client().post(f'/forms/submit/{event_id}', data=form).status_code == 302
    return event_id, title, [lead] + [m.lower() for m in mates]


def _to_any_case(sent, email, subject_start=''):
    return [m for m in sent if [t['email'].lower() for t in m['to']] == [email.lower()]
            and m['subject'].startswith(subject_start)]


def test_listed_members_and_a_joiner_get_the_confirmation_once(site, brevo):
    d = site
    event_id, title, people = _team(d, _day(10))
    for email in people:
        assert len(_to_any_case(brevo, email, 'Registration Confirmed')) == 1, email
    [reg] = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]
    # A fourth person joins with the invite code; joining twice sends nothing more
    joiner = f"{_unique('joiner')}@test.edu"
    _user(d['db'], joiner, 'Student')
    client = _login(d['app'], joiner, 'Student')
    for _ in range(2):
        client.post('/teams/join', data={'join_code': reg['team_code']})
    assert len(_to_any_case(brevo, joiner, 'Registration Confirmed')) == 1


def test_the_day_before_ticket_reaches_each_member_once(site, brevo):
    d = site
    event_id, title, people = _team(d, _day(1))
    brevo.clear()
    for _ in range(2):
        assert d['app'].test_client().post('/internal/cron/reminders', headers={'X-Cron-Secret': CRON}).status_code == 200
    for email in people:
        assert [m['subject'] for m in _to_any_case(brevo, email)] == [f'✅ Registered — {title}'], email


def test_a_venue_change_and_a_cancellation_reach_each_member_once(site, brevo):
    d = site
    event_id, title, people = _team(d, _day(10))
    brevo.clear()
    for _ in range(2):
        d['owner'].post(f'/spoc/edit_event/{event_id}', data={'venue': 'Hall C', 'title': title})
    for email in people:
        assert len(_to_any_case(brevo, email, f'Update: {title}')) == 1, email
    brevo.clear()
    for _ in range(2):
        d['owner'].post(f'/spoc/event/{event_id}/transition', data={'target_state': 'cancelled'})
    for email in people:
        assert len(_to_any_case(brevo, email, f'Cancelled: {title}')) == 1, email
    assert not _to(brevo, 'nobody@test.edu')
