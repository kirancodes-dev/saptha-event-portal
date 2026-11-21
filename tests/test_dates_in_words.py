"""
tests/test_dates_in_words.py — UPG-365: the pages that printed a stored date
as it is ("2031-03-20") say it in words ("20 Mar 2031"), as the student's
dashboard always did: the public event page's header, "Key dates" and share
text, the admin's dashboard and events list, and the coordinator's card.
"""
import datetime
import re

import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _words(response):
    """What a person reads: no tags, attributes, scripts or styles."""
    html = response.get_data(as_text=True)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return re.sub(r'<[^>]+>', ' ', html)


@pytest.fixture
def dated(real_app):
    flask_app, db = real_app
    spoc, coord, admin = (f"{_unique(k)}@test.edu" for k in ('dspoc', 'dcoord', 'dadmin'))
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    _user(db, admin, 'SuperAdmin')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Dated Event'), '2031-03-20', team=False)
    db.collection('events').document(event_id).update(
        {'status': 'active', 'end_date': '2031-03-21', 'reg_deadline': '2031-03-18'})
    assert owner.post(f'/spoc/assign_coordinator/{event_id}', data={
        'coordinator_email': coord, 'coordinator_name': 'Cora'}).status_code == 302
    return {'app': flask_app, 'id': event_id, 'coord': coord, 'admin': admin}


def test_each_page_says_the_date_in_words(dated):
    d = dated
    page = _words(d['app'].test_client().get(f"/event/{d['id']}"))
    assert '20 Mar 2031 – 21 Mar 2031' in page            # the header
    assert '18 Mar 2031' in page                           # Key dates: the registration deadline
    assert 'on%2020%20Mar%202031' in d['app'].test_client().get(f"/event/{d['id']}").get_data(as_text=True)  # share text

    admin = _login(d['app'], d['admin'], 'SuperAdmin')
    today = datetime.date.today()
    dash = _words(admin.get('/admin/dashboard'))
    assert f'Platform overview for {rs.day_text(today.isoformat())}' in dash
    assert f'Platform overview for {today.isoformat()}' not in dash   # (the activity feed's times are UPG-297 (a))

    events = _words(admin.get(f"/admin/events?q={d['id'][:8]}"))
    assert '20 Mar 2031' in events

    coord = _words(_login(d['app'], d['coord'], 'EventCoordinator').get('/coordinator/dashboard'))
    assert re.search(r'Deadline:\s*18 Mar 2031', coord)

    for words in (page, events, coord):
        assert not re.search(r'2031-03-(18|20|21)', words)
