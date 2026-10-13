"""
tests/test_event_creation.py — UPG-73 (event creation for every kind of event)
and UPG-74 (fests with sub-events), on the real SQL layer.

Every kind of event in services_event_types.TYPES can be created from the
wizard's form as a draft; bad input is refused with every message; nothing the
wizard sends is lost or replaced by placeholders; publishing opens registration
(or asks for approval in a unit); drafts and private events stay out of the
public listings; a faculty fee is charged to faculty; a fest holds sub-events
inside its dates.
"""
import datetime
import json
import re

import pytest

from services_event_types import TYPES, parse_form
from tests.test_integration_flow import _login, _unique, _user

TODAY = datetime.date.today()


def _day(n):
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def _form(key, title, **extra):
    """A complete wizard form for one kind of event."""
    spec = TYPES[key]
    data = {
        'event_type': key, 'title': title, 'description': 'A clear description of what happens and for whom.',
        'date': _day(10), 'time': '10:00', 'end_date': _day(11), 'end_time': '17:00',
        'reg_deadline': _day(8), 'venue': 'Main auditorium', 'event_mode': 'offline',
        'max_participants': '40', 'reg_fee': '0',
    }
    if spec['fest']:
        data.pop('reg_deadline')
    for f in spec['details']:
        name = f"detail_{key}__{f['name']}"
        if f['kind'] == 'select':
            data[name] = f['options'][0]
        elif f['kind'] == 'number':
            data[name] = '2'
        elif f['kind'] == 'date':
            data[name] = _day(5)
        else:
            data[name] = 'Detail text'
    if key == 'sports_tournament':
        data[f'detail_{key}__sport'] = 'Football'
    if spec['placement']:
        data['placement_company'] = 'Infosys'
    data.update(extra)
    return data


@pytest.fixture
def spoc(real_app, monkeypatch):
    flask_app, db = real_app
    import routes_spoc
    monkeypatch.setattr(routes_spoc, 'db', db)
    email = f"{_unique('evspoc')}@test.edu"
    _user(db, email, 'ClubSPOC', name='Event SPOC')
    db.collection('users').document(email).update({'phone': '+91 90000 00001'})
    return {'app': flask_app, 'db': db, 'email': email, 'client': _login(flask_app, email, 'ClubSPOC')}


def _create(client, data):
    return client.post('/spoc/create_event', data=data)


def _event_id(resp):
    m = re.search(r'/spoc/event/([^/]+)/review', resp.headers.get('Location', ''))
    assert m, (resp.status_code, resp.headers.get('Location'), resp.get_data(as_text=True)[:400])
    return m.group(1)


def _get(db, event_id):
    return db.collection('events').document(event_id).get().to_dict() or {}


# ── UPG-73 criterion 1: every kind of event, saved as a draft ───────────────

@pytest.mark.parametrize('key', sorted(TYPES))
def test_every_kind_of_event_is_created_as_a_draft(spoc, key):
    title = _unique(f'Kind {key}')
    resp = _create(spoc['client'], _form(key, title, event_mode=TYPES[key]['mode'],
                                         online_link='https://meet.example.com/abc',
                                         fee_faculty='300', allowed_participants=['student', 'faculty']))
    event_id = _event_id(resp)
    ev = _get(spoc['db'], event_id)
    assert ev['status'] == 'draft'
    assert ev['event_type'] == key
    assert ev['category'] == TYPES[key]['category']
    assert ev['event_mode'] == TYPES[key]['mode']
    assert ev['date'] == _day(10) and ev['end_date'] == _day(11) and ev['end_time'] == '17:00'
    for f in TYPES[key]['details']:
        assert ev['details'].get(f['name']), f['name']
    if TYPES[key]['fest']:
        assert ev['is_fest'] is True and ev['capacity'] == 0
    else:
        assert ev['allowed_participants'] == ['student', 'faculty']
        assert ev['fees']['faculty'] == 300.0
        assert ev['reg_deadline'] == _day(8)
    if TYPES[key]['placement']:
        assert ev['is_placement'] is True and ev['placement']['company'] == 'Infosys'


def test_team_rules_and_judging_are_kept(spoc):
    crit = [{'name': 'Innovation', 'max_score': 20, 'description': 'New ideas'}, {'name': 'Demo', 'max_score': 10}]
    event_id = _event_id(_create(spoc['client'], _form(
        'hackathon', _unique('Hack'), participation_type='Team', team_min='2', team_max='5', max_teams='30',
        total_rounds='3', judging_criteria_json=json.dumps(crit), prize_1='₹10,000', prize_pool='₹20,000')))
    ev = _get(spoc['db'], event_id)
    assert ev['is_team_event'] is True
    assert (ev['limits']['team_min'], ev['limits']['team_max'], ev['limits']['max_teams']) == (2, 5, 30)
    assert ev['total_rounds'] == 3
    assert [c['name'] for c in ev['judging_criteria']] == ['Innovation', 'Demo']
    assert ev['prizes'] == {'1st': '₹10,000'} and ev['prize_pool'] == '₹20,000'


# ── Criterion 2: bad input is refused with every message ────────────────────

def test_invalid_input_is_refused_with_every_message(spoc):
    title = _unique('Broken Cup')
    resp = _create(spoc['client'], {
        'event_type': 'sports_tournament', 'title': '', 'date': _day(10), 'end_date': _day(9),
        'reg_deadline': _day(12), 'event_mode': 'hybrid', 'venue': 'Ground',
        'online_link': 'http://insecure.example.com', 'participation_type': 'Team',
        'team_min': '9', 'team_max': '5'})
    assert resp.status_code == 400
    page = resp.get_data(as_text=True)
    for msg in ('Give the event a title.', 'The event ends before it starts.',
                'Registration must close on or before the last day of the event.',
                'The online meeting link must start with https://.',
                'The smallest team is larger than the largest team.',
                'Sport is required for a sports tournament.'):
        assert msg in page, msg
    assert not list(spoc['db'].collection('events').where('title', '==', title).stream())


def test_a_bad_form_keeps_what_was_typed(spoc):
    resp = _create(spoc['client'], _form('quiz', 'Kept Title Quiz', reg_deadline=_day(30)))
    assert resp.status_code == 400
    assert 'value="Kept Title Quiz"' in resp.get_data(as_text=True)


def test_a_past_event_can_be_recorded_with_a_warning(spoc):
    event_id = _event_id(_create(spoc['client'], _form('social_drive', _unique('Past Drive'),
                                                       date=_day(-3), end_date=_day(-3), reg_deadline=_day(-4))))
    ev = _get(spoc['db'], event_id)
    assert ev['status'] == 'draft'
    assert any('past' in w for w in ev['warnings'])


# ── Criterion 3: nothing the wizard sends is lost, no placeholders ─────────

def test_extras_are_stored_and_there_are_no_placeholders(spoc):
    sponsors = [{'name': 'Decathlon', 'tier': 'Gold', 'logo_url': 'https://cdn.example/logo.png',
                 'website': 'javascript:alert(1)'}]
    event_id = _event_id(_create(spoc['client'], _form(
        'cultural_competition', _unique('Dance Off'), map_link='https://maps.example/x',
        group_link='https://chat.whatsapp.com/abc', sponsors_json=json.dumps(sponsors), prize_pool='₹5,000')))
    ev = _get(spoc['db'], event_id)
    assert ev['map_link'] == 'https://maps.example/x'
    assert ev['prize_pool'] == '₹5,000'
    assert ev['sponsors'] == [{'name': 'Decathlon', 'tier': 'Gold', 'logo_url': 'https://cdn.example/logo.png',
                               'website': ''}]
    assert ev['organizer']['group_link'] == 'https://chat.whatsapp.com/abc'
    assert ev['organizer']['phone'] == '+91 90000 00001'          # from the SPOC's profile
    assert '9999999999' not in json.dumps(ev) and 'placehold.co' not in json.dumps(ev)
    assert ev['organizer']['group_link'] != '#'


# ── Criterion 4: publishing ────────────────────────────────────────────────

def test_publishing_a_central_event_opens_registration(spoc):
    import routes_forms
    event_id = _event_id(_create(spoc['client'], _form('workshop', _unique('Open Lab'))))
    assert routes_forms.registration_closed(_get(spoc['db'], event_id))   # a draft takes no registrations
    resp = spoc['client'].post(f'/spoc/event/{event_id}/publish')
    assert resp.status_code == 302
    ev = _get(spoc['db'], event_id)
    assert ev['status'] == 'registration_open'
    assert not routes_forms.registration_closed(ev)


def test_publishing_a_unit_event_asks_for_approval(spoc):
    db = spoc['db']
    unit = _unique('unit')
    db.collection('org_units').document(unit).set({'name': 'Unit X', 'type': 'department', 'parent_id': 'central'})
    db.collection('users').document(spoc['email']).update({'department': unit})
    event_id = _event_id(_create(spoc['client'], _form('seminar', _unique('Unit Talk'))))
    assert _get(db, event_id)['org_unit_id'] == unit
    spoc['client'].post(f'/spoc/event/{event_id}/publish')
    assert _get(db, event_id)['status'] == 'pending_approval'


def test_a_department_that_isnt_a_unit_doesnt_break_the_save(spoc):
    db = spoc['db']
    db.collection('users').document(spoc['email']).update({'department': 'Computer Science & Engineering'})
    event_id = _event_id(_create(spoc['client'], _form('club_activity', _unique('Club Meet'))))
    ev = _get(db, event_id)
    assert ev['org_unit_id'] == 'central' and ev['department'] == 'Computer Science & Engineering'


def test_editing_in_the_wizard_saves_changes_and_keeps_the_status(spoc):
    db = spoc['db']
    event_id = _event_id(_create(spoc['client'], _form('quiz', _unique('Quiz Night'))))
    spoc['client'].post(f'/spoc/event/{event_id}/publish')
    page = spoc['client'].get(f'/spoc/event/{event_id}/setup').get_data(as_text=True)
    assert 'Quiz Night' in page
    resp = spoc['client'].post(f'/spoc/event/{event_id}/setup',
                               data=_form('quiz', 'Quiz Night (moved)', venue='Seminar hall 2'))
    assert resp.status_code == 302
    ev = _get(db, event_id)
    assert ev['title'] == 'Quiz Night (moved)' and ev['venue'] == 'Seminar hall 2'
    assert ev['status'] == 'registration_open'


# ── Criterion 5: listings ──────────────────────────────────────────────────

def test_drafts_and_private_events_are_not_listed(spoc):
    client, db = spoc['client'], spoc['db']
    draft = _event_id(_create(client, _form('seminar', _unique('Hidden Draft'))))
    private = _event_id(_create(client, _form('seminar', _unique('Link Only'), visibility='Private')))
    public = _event_id(_create(client, _form('seminar', _unique('Open Talk'))))
    for eid in (private, public):
        client.post(f'/spoc/event/{eid}/publish')
    visitor = spoc['app'].test_client()
    for url in ('/events?format=json', '/?format=json'):
        listed = visitor.get(url).get_data(as_text=True)
        assert public in listed, url
        assert draft not in listed and private not in listed, url
    assert visitor.get(f'/event/{draft}').status_code == 404
    assert visitor.get(f'/event/{private}').status_code == 200      # reachable by its link
    assert client.get(f'/spoc/event/{draft}/review').status_code == 200


def test_another_spoc_cant_review_or_publish_my_draft(spoc):
    draft = _event_id(_create(spoc['client'], _form('seminar', _unique('Mine'))))
    other = f"{_unique('otherspoc')}@test.edu"
    _user(spoc['db'], other, 'ClubSPOC')
    stranger = _login(spoc['app'], other, 'ClubSPOC')
    assert stranger.get(f'/spoc/event/{draft}/review').status_code == 403
    assert stranger.post(f'/spoc/event/{draft}/publish').status_code == 403
    assert _get(spoc['db'], draft)['status'] == 'draft'


# ── Criterion 6: fees per group ────────────────────────────────────────────

def test_faculty_are_charged_the_faculty_fee(spoc):
    from services_payments import fee_for, server_price
    event_id = _event_id(_create(spoc['client'], _form('fdp', _unique('FDP'), reg_fee='500', fee_faculty='1200',
                                                       allowed_participants=['faculty', 'student'])))
    ev = _get(spoc['db'], event_id)
    assert fee_for(ev, 'faculty') == 1200.0
    assert fee_for(ev, 'student') == 500.0 and fee_for(ev, '') == 500.0
    assert server_price(spoc['db'], event_id, ev, '', 'faculty')['amount_inr'] == 1200.0
    assert server_price(spoc['db'], event_id, ev)['amount_inr'] == 500.0


def test_a_free_event_with_a_paid_group_charges_only_that_group():
    from services_payments import fee_for
    ev = {'entry_fee': 0, 'fees': {'regular': 0, 'external': 250}}
    assert fee_for(ev, 'external') == 250.0
    assert fee_for(ev, 'student') == 0.0


# ── UPG-74: fests ──────────────────────────────────────────────────────────

def _fest(spoc, start=12, end=14):
    return _event_id(_create(spoc['client'], _form('fest', _unique('Utsav'), date=_day(start), end_date=_day(end))))


def test_a_fest_holds_sub_events_inside_its_dates(spoc):
    db = spoc['db']
    fest = _fest(spoc)
    assert _get(db, fest)['is_fest'] is True and _get(db, fest)['status'] == 'draft'
    inside = _event_id(_create(spoc['client'], _form('cultural_competition', _unique('Battle of Bands'),
                                                     parent_event_id=fest, date=_day(13), end_date=_day(13),
                                                     reg_deadline=_day(11))))
    assert _get(db, inside)['parent_event_id'] == fest
    outside = _create(spoc['client'], _form('quiz', _unique('Too Late Quiz'), parent_event_id=fest,
                                            date=_day(20), end_date=_day(20), reg_deadline=_day(11)))
    assert outside.status_code == 400 and 'must take place during the fest' in outside.get_data(as_text=True)
    review = spoc['client'].get(f'/spoc/event/{fest}/review').get_data(as_text=True)
    assert 'Battle of Bands' in review


def test_only_the_fests_owner_can_add_to_it(spoc):
    fest = _fest(spoc)
    other = f"{_unique('festother')}@test.edu"
    _user(spoc['db'], other, 'ClubSPOC')
    stranger = _login(spoc['app'], other, 'ClubSPOC')
    resp = stranger.post('/spoc/create_event', data=_form('quiz', _unique('Gatecrash'), parent_event_id=fest,
                                                         date=_day(13), end_date=_day(13), reg_deadline=_day(11)))
    assert resp.status_code == 302 and '/spoc/dashboard' in resp.headers['Location']
    assert not [d for d in spoc['db'].collection('events').where('parent_event_id', '==', fest).stream()]


def test_the_fest_page_lists_published_sub_events_only(spoc):
    client = spoc['client']
    fest = _fest(spoc)
    shown = _event_id(_create(client, _form('quiz', _unique('Shown Quiz'), parent_event_id=fest,
                                            date=_day(13), end_date=_day(13), reg_deadline=_day(11))))
    hidden = _event_id(_create(client, _form('debate', _unique('Draft Debate'), parent_event_id=fest,
                                             date=_day(13), end_date=_day(13), reg_deadline=_day(11))))
    client.post(f'/spoc/event/{fest}/publish')
    client.post(f'/spoc/event/{shown}/publish')
    visitor = spoc['app'].test_client()
    page = visitor.get(f'/event/{fest}').get_data(as_text=True)
    assert f'/event/{shown}' in page and f'/event/{hidden}' not in page
    assert 'class="reg-bar"' not in page                   # a fest has no registration of its own
    # The same programme whichever form of the fest's id the link uses
    plain = visitor.get(f"/event/{fest.replace('-', '')}").get_data(as_text=True)
    assert f'/event/{shown}' in plain
    sub = visitor.get(f'/event/{shown}').get_data(as_text=True)
    assert f'/event/{fest}' in sub                          # links back to its fest


def test_parse_form_rejects_a_fest_inside_a_fest():
    data, errors, _ = parse_form(_form('fest', 'Nested'), parent={'id': 'f1', 'date': _day(10), 'end_date': _day(12)})
    assert any("can't be added inside another fest" in e for e in errors)
