"""
tests/test_jersey_numbers.py — the owner, 23 Nov 2026: "same jersey no can
be used … allow SPOC to edit jersey no". UPG-460: two players of a team may
share a number. UPG-461: the SPOC's Jersey numbers page, every team on one
page, saved at once, and the line-ups of matches not yet over take the new
numbers. All names here are made up.
"""
import re

import services_live_match as live
from tests.test_integration_flow import _login, _unique, _user
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import AWAY, HOME, _lineups, _match, _people
from tests.test_sports_team_details import SPORTS, _regs, _send, sports_form, stored  # noqa: F401
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_team_member_confirm import team  # noqa: F401


def test_two_players_of_a_team_may_register_with_the_same_number(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](2)
    _, resp = _send(t, event_id, mates, **sports_form(2, lead='7', numbers={1: '7', 2: '07'}))
    assert resp.status_code == 302
    regs = _regs(t, event_id)
    assert len(regs) == 1
    assert sorted(m.get('jersey') for m in regs[0]['members']) == ['7', '7', '7']
    # A missing number is still refused
    _, resp = _send(t, event_id, t['mates'](2), team_name='Neuro Ninjas', **sports_form(2, numbers={2: ''}))
    assert len(_regs(t, event_id)) == 1


def _squads(d, event_id, ids):
    m = _match(d, event_id, ids)
    homes = _people(d, m['home'], HOME, 'h')
    aways = _people(d, m['away'], AWAY, 'a')
    live._cache.clear()
    return m, homes, aways


def _jerseys(d, event_id):
    return d['owner'].get(f'/tournament/{event_id}/jerseys').get_data(as_text=True)


def test_the_spoc_changes_every_teams_numbers_on_one_page(league):  # noqa: F811
    d, event_id, ids = league
    m, homes, aways = _squads(d, event_id, ids)
    _lineups(d, event_id, m)                                   # saved with the old numbers
    assert 'data-jerseys-link' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    page = _jerseys(d, event_id)
    assert page.count('data-jersey-team=') == 8                # every team, the ones without numbers too
    lead, bharat, deepak = (f"j|{m['home']}|lead", f"j|{m['home']}|{homes['Bharat']}",
                            f"j|{m['away']}|{aways['Deepak']}")
    for name in (lead, bharat, deepak):
        assert f'name="{name}"' in page
    assert re.search(rf'name="{re.escape(bharat)}" value="1"', page)

    resp = d['owner'].post(f'/tournament/{event_id}/jerseys', follow_redirects=True,
                           data={lead: '8', bharat: '077', deepak: '3', f"j|{m['away']}|lead": '7'})
    said = resp.get_data(as_text=True)
    assert 'Saved 3 jersey numbers' in said and '1 match line-up updated too' in said
    assert re.search(r'Note: [^<]*Deepak and Ganesh both wear 3', said) or \
        re.search(r'Note: [^<]*Ganesh and Deepak both wear 3', said)
    # Written where the registration keeps it, and where the scorer and the pages read it
    home_reg = d['db'].collection('registrations').document(m['home']).get().to_dict()
    assert home_reg['lead_jersey'] == '8'
    assert {x['name']: x['jersey'] for x in home_reg['members']}['Bharat'] == '77'
    numbers = live.jerseys(d['db'], event_id, [m['home'], m['away']])
    assert numbers[m['home']]['Arjun'] == '8' and numbers[m['home']]['Bharat'] == '77'
    assert numbers[m['away']]['Deepak'] == '3'
    doc = live.get(d['db'], event_id, m['id'])
    assert live.jersey_of(doc, 'home', 'Bharat') == '77' and live.jersey_of(doc, 'away', 'Deepak') == '3'
    assert live.jersey_of(doc, 'home', 'Chetan') == '3'           # the others as they were
    # The page marks the shared number
    page = _jerseys(d, event_id)
    assert len(re.findall(r'data-jersey-shared', page)) >= 2


def test_a_wrong_number_saves_nothing_and_a_finished_match_keeps_its_numbers(league):  # noqa: F811
    d, event_id, ids = league
    m, homes, _ = _squads(d, event_id, ids)
    _lineups(d, event_id, m)
    bharat, chetan = f"j|{m['home']}|{homes['Bharat']}", f"j|{m['home']}|{homes['Chetan']}"
    page = d['owner'].post(f'/tournament/{event_id}/jerseys',
                           data={bharat: '1000', chetan: '30'}).get_data(as_text=True)
    assert 'nothing was saved' in page and 'data-jersey-error' in page and 'value="1000"' in page
    numbers = live.jerseys(d['db'], event_id, [m['home']])[m['home']]
    assert numbers['Bharat'] == '1' and numbers['Chetan'] == '3'
    # Nothing changed is said so
    resp = d['owner'].post(f'/tournament/{event_id}/jerseys', data={bharat: '1'}, follow_redirects=True)
    assert 'Nothing was changed.' in resp.get_data(as_text=True)
    # A match already over keeps the numbers it was played in
    doc = live.get(d['db'], event_id, m['id'])
    doc['phase'] = 'full_time'
    d['db'].collection(live.COLLECTION).document(live.doc_id(event_id, m['id'])).set(doc)
    resp = d['owner'].post(f'/tournament/{event_id}/jerseys', data={bharat: '41'}, follow_redirects=True)
    assert 'Saved 1 jersey number' in resp.get_data(as_text=True)
    assert live.jersey_of(live.get(d['db'], event_id, m['id']), 'home', 'Bharat') == '1'


def test_only_the_events_organisers_open_the_page(league):  # noqa: F811
    d, event_id, ids = league
    student = f"{_unique('fan')}@test.edu"
    _user(d['db'], student, 'Student')
    other = _login(d['app'], student, 'Student')
    assert other.get(f'/tournament/{event_id}/jerseys').status_code == 403
    assert other.post(f'/tournament/{event_id}/jerseys', data={}).status_code == 403
