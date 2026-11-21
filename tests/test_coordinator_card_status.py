"""
tests/test_coordinator_card_status.py — UPG-362: the coordinator's event card
says what visitors see, in the SPOC console's words. An event that hasn't
started isn't "Closed" or "concluded", and the card has no one-click delete.
"""
import datetime
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def coordinated(real_app):
    flask_app, db = real_app
    owner, coord = f"{_unique('owner')}@test.edu", f"{_unique('coord')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    spoc = _login(flask_app, owner, 'ClubSPOC')
    today = datetime.date.today()
    ids = {}
    for key, days, fields in (
        ('soon', 5, {'status': 'published', 'reg_opens': (today + datetime.timedelta(days=2)).isoformat()}),
        ('open', 5, {'status': 'active', 'reg_opens': '', 'deadline': ''}),
        ('over', 0, {'status': 'completed'}),
    ):
        title = _unique(f'Card {key}')
        event_id = _create_event(spoc, db, title, (today + datetime.timedelta(days=days)).isoformat(), team=False)
        assert spoc.post(f'/spoc/assign_coordinator/{event_id}', data={
            'coordinator_email': coord, 'coordinator_name': 'Cora'}).status_code == 302
        db.collection('events').document(event_id).update(fields)
        ids[key] = event_id
    page = _login(flask_app, coord, 'EventCoordinator').get('/coordinator/dashboard').get_data(as_text=True)
    return {'page': page, 'ids': ids}


def _card(page, event_id):
    found = re.search(rf'data-event-card="{event_id}"(.*?)(?=data-event-card=|<!-- ── MODALS)', page, re.S)
    assert found, event_id
    return found.group(1)


def _badge(card):
    return re.search(r'data-organiser-status="([^"]*)"[^>]*>([^<]*)<', card).groups()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_an_event_that_has_not_started_opens_soon_and_only_an_ended_one_is_concluded(coordinated):
    page, ids = coordinated['page'], coordinated['ids']

    soon = _card(page, ids['soon'])
    assert _badge(soon) == ('not_open', 'Opens soon')
    assert 'Closed' not in soon and 'Event concluded' not in soon and 'Export final data' not in soon
    assert f'/coordinator/registrations/{ids["soon"]}' in soon  # its students are still one tap away

    live = _card(page, ids['open'])
    assert _badge(live) == ('open', 'Registration open')
    assert 'Event concluded' not in live

    over = _card(page, ids['over'])
    assert _badge(over) == ('ended', 'Event over')
    assert 'Event concluded' in over and 'Export final data' in over


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_coordinator_dashboard_has_no_delete_form(coordinated):
    page = coordinated['page']
    assert '/coordinator/delete_event/' not in page
    assert 'Delete event' not in page
