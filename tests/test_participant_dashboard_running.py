"""
tests/test_participant_dashboard_running.py — UPG-335 on the real database
layer: a two-day event (SAPTHAHACKS'26: 19 → 20 Nov) stays in the student's
"My active tickets", marked "Happening now", until its last day has passed,
counted in India's date (the server's clock is UTC, a day behind until 05:30
IST). Only then does it move to "Past events", where the lead still finds the
hackathon page; a member doesn't (only the lead opens it, UPG-196).
"""
import datetime

import routes_participant
from tests import test_registration_edit as _edit
from tests.test_integration_flow import _login, _user

team = _edit.team   # the lead Lena, members Hima and Alif (UPG-225's fixture)

TODAY = datetime.date(2026, 11, 20)


def _set(t, **fields):
    if 'end_date' in fields:     # an event's end date and end time go together (services_event_types)
        fields['end_datetime'] = f"{fields['end_date'] or fields['date']}T18:00"
    t['db'].collection('events').document(t['event_id']).update(fields)


def _days(n):
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def _sections(client):
    resp = client.get('/participant/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    start = html.index('<div id="tickets-section">')
    split = html.find('<div id="past">')                   # only there when something is past
    end = html.index('id="profile-section"')
    return html[start:split if split > 0 else end], (html[split:end] if split > 0 else '')


def _on(monkeypatch, day=TODAY):
    monkeypatch.setattr(routes_participant, '_ist_today', lambda: day)


def test_a_two_day_event_on_its_second_day_is_active_and_happening_now(team, monkeypatch):
    t = team
    _on(monkeypatch)
    _set(t, date=_days(-1), end_date=_days(0), status='registration_closed', event_type='hackathon')
    active, past = _sections(t['lead_client'])
    ticket = f"/ticket/{t['reg_id']}"
    assert ticket in active and ticket not in past
    assert 'data-happening-now' in active and 'Happening now' in active


def test_an_event_in_progress_stays_active_after_its_dates(team, monkeypatch):
    t = team
    _on(monkeypatch)
    _set(t, date=_days(-3), end_date=_days(-2), status='in_progress')
    active, _ = _sections(t['lead_client'])
    assert f"/ticket/{t['reg_id']}" in active and 'data-happening-now' in active


def test_an_event_whose_last_day_has_passed_is_past(team, monkeypatch):
    t = team
    _on(monkeypatch)
    _set(t, date=_days(-2), end_date=_days(-1), status='registration_closed')
    active, past = _sections(t['lead_client'])
    assert f"/ticket/{t['reg_id']}" not in active and 'data-happening-now' not in active
    assert 'Edit Hack' in past


def test_a_one_day_event_today_is_today_not_happening_now(team, monkeypatch):
    t = team
    _on(monkeypatch)
    _set(t, date=_days(0), end_date='', status='registration_closed')
    active, _ = _sections(t['lead_client'])
    assert f"/ticket/{t['reg_id']}" in active
    assert 'Today!' in active and 'data-happening-now' not in active


def test_the_day_is_indias_not_the_servers_utc(team, monkeypatch):
    """At 02:00 IST on 21 Nov the server's UTC date is still 20 Nov: the event
    that ended on 20 Nov is past for the student in India."""
    t = team
    _set(t, date=_days(-1), end_date=_days(0), status='registration_closed')

    class _Clock(datetime.datetime):
        @classmethod
        def now(cls, tz: "datetime.tzinfo | None" = None) -> "_Clock":   # type: ignore[override]
            ist = cls(2026, 11, 21, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            return ist.astimezone(tz) if tz else ist.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    with monkeypatch.context() as clock:       # only around the call: sign-in checks use the clock too
        clock.setattr(routes_participant.datetime, 'datetime', _Clock)
        india = routes_participant._ist_today()
        server = _Clock.now().date()
    assert (india, server) == (datetime.date(2026, 11, 21), datetime.date(2026, 11, 20))
    _on(monkeypatch, server)
    assert f"/ticket/{t['reg_id']}" in _sections(t['lead_client'])[0]       # by the server's date: still on
    _on(monkeypatch, india)
    assert f"/ticket/{t['reg_id']}" not in _sections(t['lead_client'])[0]   # in India it has ended


def test_the_leads_past_card_has_the_hackathon_page_and_a_members_doesnt(team, monkeypatch):
    t = team
    _on(monkeypatch)
    _set(t, date=_days(-2), end_date=_days(-1), status='registration_closed', event_type='hackathon')
    _, lead_past = _sections(t['lead_client'])
    assert f'href="/hackathon/{t["event_id"]}"' in lead_past and 'data-hackathon-page' in lead_past
    _user(t['db'], t['hima'], 'Student')
    _, member_past = _sections(_login(t['app'], t['hima'], 'Student'))
    assert 'Edit Hack' in member_past and 'data-hackathon-page' not in member_past
