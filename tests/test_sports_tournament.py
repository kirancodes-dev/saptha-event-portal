"""
tests/test_sports_tournament.py — UPG-13 on the real database layer, through the
routes: 8 teams make a 7-match knockout whose results carry the winners to one
champion; a 4-team league's table is right after its 6 results; only the SPOC
or an assigned coordinator can enter results (and only the SPOC can generate);
the public fixtures page needs no login.
"""
import datetime

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def cup(real_app):
    flask_app, db = real_app
    spoc, coord = f"{_unique('cupspoc')}@test.edu", f"{_unique('cupcoord')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()

    def event(team_names):
        event_id = _create_event(owner, db, _unique('Cup'), day, team=True)
        db.collection('events').document(event_id).update({
            'category': 'Sports', 'staff': [{'name': 'Cora', 'email': coord, 'role': 'EventCoordinator'}]})
        for i, name in enumerate(team_names):
            db.collection('registrations').document(_unique('REG')).set({
                'event_id': event_id, 'team_name': name, 'lead_name': f'{name} lead',
                'lead_email': f"{_unique('cap')}@test.edu", 'status': 'Confirmed',
                'registered_at': f'2026-10-01 10:00:{i:02d}'})
        # A cancelled team isn't drawn
        db.collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'team_name': 'Withdrawn XI', 'lead_email': f"{_unique('cap')}@test.edu",
            'status': 'Cancelled', 'registered_at': '2026-10-01 09:00:00'})
        # The ids as stored (the SQL layer keeps a registration's id as a uuid)
        ids = {r.to_dict()['team_name']: r.id
               for r in db.collection('registrations').where('event_id', '==', event_id).stream()}
        return event_id, ids

    return {'app': flask_app, 'db': db, 'owner': owner, 'coord': _login(flask_app, coord, 'EventCoordinator'),
            'coord_email': coord, 'event': event}


def _t(d, event_id):
    return d['db'].collection('events').document(event_id).get().to_dict().get('tournament') or {}


def _play(client, event_id, m, home, away, winner=''):
    resp = client.post(f"/tournament/{event_id}/match/{m['id']}/result",
                       data={'home_score': str(home), 'away_score': str(away), 'winner': winner})
    assert resp.status_code == 302


def test_eight_teams_make_a_seven_match_knockout_with_one_champion(cup):
    d = cup
    names = [f'Team {c}' for c in 'ABCDEFGH']
    event_id, ids = d['event'](names)
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    t = _t(d, event_id)
    assert t['format'] == 'knockout' and len(t['matches']) == 7
    assert {x['name'] for x in t['teams']} == set(names)          # the cancelled team isn't drawn
    assert all(m['status'] == 'scheduled' for m in t['matches'])  # 8 teams: no byes

    # Round by round, the home side wins, except one tie decided for the away side
    for rnd in (1, 2, 3):
        for m in [m for m in _t(d, event_id)['matches'] if m['round'] == rnd]:
            assert m['home'] and m['away'], m                      # both winners arrived
            if m['id'] == 'm2':
                _play(d['owner'], event_id, m, 1, 1, winner=m['away'])
            else:
                _play(d['owner'], event_id, m, 2, 0)

    t = _t(d, event_id)
    by_id = {m['id']: m for m in t['matches']}
    final = [m for m in t['matches'] if not m.get('next')]
    assert len(final) == 1 and final[0]['status'] == 'played'
    assert by_id['m2']['winner'] == by_id['m2']['away']           # the tie-break winner went through
    champion = final[0]['winner']
    assert champion == ids['Team A']
    page = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'Champion: Team A' in page


def test_a_four_team_league_table_is_right_after_six_results(cup):
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    t = _t(d, event_id)
    assert t['format'] == 'league' and len(t['matches']) == 6
    name = {v: k for k, v in ids.items()}
    scores = {('Ants', 'Bees'): (2, 1), ('Ants', 'Cats'): (1, 1), ('Ants', 'Dogs'): (3, 0),
              ('Bees', 'Cats'): (0, 2), ('Bees', 'Dogs'): (2, 2), ('Cats', 'Dogs'): (1, 0)}
    for m in t['matches']:
        home, away = name[m['home']], name[m['away']]
        if (home, away) in scores:
            h, a = scores[(home, away)]
        else:
            a, h = scores[(away, home)]
        _play(d['coord'], event_id, m, h, a)                      # the assigned coordinator enters them

    assert d['owner'].get(f'/tournament/{event_id}').status_code == 200
    import services_sports
    table = [(r['name'], r['played'], r['won'], r['drawn'], r['lost'], r['for'], r['against'], r['points'])
             for r in services_sports.standings(_t(d, event_id))]
    assert table == [('Ants', 3, 2, 1, 0, 6, 2, 7),                # 7 points, +4 goal difference
                     ('Cats', 3, 2, 1, 0, 4, 1, 7),                # 7 points, +3
                     ('Bees', 3, 0, 1, 2, 3, 6, 1),                # 1 point, -3
                     ('Dogs', 3, 0, 1, 2, 2, 6, 1)]                # 1 point, -4
    page = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    shown = page[page.index('Points table'):page.index('</table>', page.index('Points table'))]
    assert shown.index('Ants') < shown.index('Cats') < shown.index('Bees') < shown.index('Dogs')


def test_only_the_spoc_or_an_assigned_coordinator_can_enter_results(cup):
    d = cup
    event_id, _ = d['event'](['Reds', 'Blues', 'Greens', 'Golds'])
    stranger_spoc, stranger_coord, student = (f"{_unique(k)}@test.edu" for k in ('otherspoc', 'othercoord', 'fan'))
    _user(d['db'], stranger_spoc, 'ClubSPOC')
    _user(d['db'], stranger_coord, 'EventCoordinator')
    _user(d['db'], student, 'Student')
    outsiders = [_login(d['app'], stranger_spoc, 'ClubSPOC'), _login(d['app'], stranger_coord, 'EventCoordinator'),
                 _login(d['app'], student, 'Student')]

    for client in outsiders + [d['coord']]:                        # generating is the SPOC's alone
        assert client.post(f'/tournament/{event_id}/generate', data={'format': 'league'}).status_code == 403
    assert _t(d, event_id) == {}
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    before = _t(d, event_id)
    first = before['matches'][0]['id']

    for client in outsiders:
        url = f'/tournament/{event_id}/match/{first}/result'
        assert client.post(url, data={'home_score': '1', 'away_score': '0'}).status_code == 403
        assert client.get(f'/tournament/{event_id}').status_code == 403
    assert _t(d, event_id) == before

    _play(d['coord'], event_id, before['matches'][0], 1, 0)
    _play(d['owner'], event_id, before['matches'][1], 0, 3)
    played = [m for m in _t(d, event_id)['matches'] if m['status'] == 'played']
    assert len(played) == 2


def test_the_public_fixtures_page_renders_without_login(cup):
    d = cup
    event_id, _ = d['event'](['North', 'South', 'East'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    anonymous = d['app'].test_client()
    page = anonymous.get(f'/tournament/fixtures/{event_id}')
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert all(n in text for n in ('North', 'South', 'East'))
    assert anonymous.get(f'/sports/fixtures/{event_id}').headers['Location'] == f'/tournament/fixtures/{event_id}'
    assert anonymous.get(f'/tournament/{event_id}').status_code in (302, 401)   # the staff page needs a login
