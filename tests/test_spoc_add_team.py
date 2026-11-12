"""
tests/test_spoc_add_team.py — UPG-244 on the real database layer.

Owner, 2026-11-12: "add the manual option for the SPOC to add the team". The
hosting SPOC opens "Add a team" on the registrations page: the event's own
form, in organiser mode. The team is saved as an online sign-up is (the lead
typed in, members, team code, answers, consent), straight into the list even
when the event is full or teams are waiting, never the waitlist; the lead gets
the registration email (with a set-password link for a new account). Nobody
else may add, a paid event can't be added by hand, and a person already
registered isn't added twice.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _unique, _user
from tests.test_spoc_waitlist import _full_event, _join, _page, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _flashes(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _, m in sess.get('_flashes', []))


def _add(client, event_id, team='Hand Made', lead=None, **extra):
    lead = lead or f"{_unique('hand')}@test.edu"
    mate = f"{_unique('handmate')}@test.edu"
    resp = client.post(f'/forms/submit/{event_id}', data=dict({
        'add': 'team', 'privacy_consent': 'yes', 'full_name': 'Hana Hand', 'email': lead,
        'phone': '9988776655', 'usn': '1sn22cs500', 'team_name': team,
        'member_1_name': 'Mina Mate', 'member_1_email': mate, 'member_1_usn': '1SN22CS501'}, **extra))
    return resp, lead, mate


def _audit(h, action):
    return [a.to_dict().get('details', '') for a in h['db'].collection('audit_log').stream()
            if a.to_dict().get('action') == action]


def test_the_hosting_spoc_adds_a_team_saved_as_an_online_sign_up(host, monkeypatch):
    h = host
    links = []
    import utils_email
    monkeypatch.setattr(utils_email, 'send_set_password_email',
                        lambda to, name, url, *a, **k: links.append((to, url, k.get('registration'))) or True)
    event_id = h['event']()
    page = _page(h['owner'], event_id)
    assert f'href="/forms/register/{event_id}?add=team"' in page and 'data-add-team' in page
    form = h['owner'].get(f'/forms/register/{event_id}?add=team')
    assert form.status_code == 200
    html = form.get_data(as_text=True)
    assert 'data-add-team-note' in html and 'name="add" value="team"' in html and 'Add this team' in html
    assert f'href="/coordinator/registrations/{event_id}"' in html          # Back goes to the list

    before = h['count'](event_id)
    h['emails'].clear()
    resp, lead, mate = _add(h['owner'], event_id)
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}')
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'Confirmed' and reg['team_name'] == 'Hand Made' and reg['lead_usn'] == '1SN22CS500'
    assert [m['email'] for m in reg['members']] == [lead, mate] and reg.get('team_code')
    assert reg['added_by'] == h['spoc'] and reg['privacy_consent']
    assert _regs_of(h, event_id, h['spoc']) == []                           # not the SPOC's own sign-up
    assert h['count'](event_id) == before + 1
    user = h['db'].collection('users').document(lead).get().to_dict()
    assert user and user.get('needs_password_reset')                        # a new account, password by link
    [(to, url, registration)] = links                                       # ONE email, to the lead:
    assert to == lead and '/set_password/' in url                           # registered, set a password
    assert registration and registration['reg_id'] == reg['reg_id'] and registration['team_name'] == 'Hand Made'
    assert 'Hand Made is registered' in _flashes(h['owner'])
    assert any(lead in d and h['spoc'] in d for d in _audit(h, 'REGISTRATION_ADDED_BY_ORGANISER'))
    assert 'Hand Made' in _page(h['owner'], event_id)


def test_added_by_hand_goes_straight_in_when_full_closed_or_teams_wait(host):
    h = host
    event_id = _full_event(h)
    h['owner'].post(f'/coordinator/registrations/{event_id}/waitlist_auto', data={'auto': 'off'})
    wl_id, waiting_lead, _ = _join(h, event_id, 'Still Waiting')
    h['db'].collection('events').document(event_id).update({'status': 'registration_closed'})

    resp, lead, _ = _add(h['owner'], event_id, team='Late Addition')
    assert resp.status_code == 302
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'Confirmed' and h['count'](event_id) == 2      # past the limit of 1
    assert not [d for d in h['db'].collection('waitlists').where('event_id', '==', event_id).stream()
                if d.to_dict().get('email') == lead]                       # never the waitlist
    assert h['db'].collection('waitlists').document(wl_id).get().to_dict()['status'] == 'waiting'
    assert 'over the limit' in _flashes(h['owner'])


def test_only_the_hosting_spoc_adds(host):
    h = host
    db, flask_app = h['db'], h['app']
    event_id = h['event']()
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(event_id).update({'coordinators': [coord]})
    student = f"{_unique('stud')}@test.edu"
    _user(db, student, 'Student')
    for email, role in ((other, 'ClubSPOC'), (coord, 'EventCoordinator'), (student, 'Student')):
        client = _login(flask_app, email, role)
        assert client.get(f'/forms/register/{event_id}?add=team').status_code == 403
        resp, lead, _ = _add(client, event_id)
        assert resp.status_code == 403 and _regs_of(h, event_id, lead) == []
    assert 'data-add-team' not in _page(_login(flask_app, coord, 'EventCoordinator'), event_id)
    anon = flask_app.test_client()
    resp, lead, _ = _add(anon, event_id)
    assert resp.status_code == 403 and _regs_of(h, event_id, lead) == []


def test_someone_already_registered_or_a_paid_event_is_not_added(host):
    h = host
    event_id = h['event']()
    reg_id, lead, _ = h['register'](event_id)
    before = h['count'](event_id)
    resp, _, _ = _add(h['owner'], event_id, lead=lead)
    assert resp.status_code == 302 and len(_regs_of(h, event_id, lead)) == 1 and h['count'](event_id) == before
    assert 'already registered' in _flashes(h['owner'])

    paid = h['event'](entry_fee=200, fees={'regular': 200})
    page = h['owner'].get(f'/forms/register/{paid}?add=team').get_data(as_text=True)
    assert 'data-add-team-paid' in page
    resp, new_lead, _ = _add(h['owner'], paid)
    assert resp.status_code == 302 and _regs_of(h, paid, new_lead) == []
    assert "can't be added by hand" in _flashes(h['owner'])


def test_a_missing_member_or_no_consent_sends_the_spoc_back_to_the_form(host):
    h = host
    event_id = h['event']()
    resp, lead, _ = _add(h['owner'], event_id, privacy_consent='')
    assert resp.headers['Location'].endswith(f'/forms/register/{event_id}?add=team')
    assert _regs_of(h, event_id, lead) == []
