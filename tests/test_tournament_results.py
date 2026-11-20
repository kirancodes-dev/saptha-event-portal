"""
tests/test_tournament_results.py — UPG-342: a tournament's places become the
event's result. `placings` reads them from the final (and the third-place match,
or else both losing semi-finalists) or from a finished league's table; publishing
from the tournament page writes each team's place, shows the place on the
winners' dashboards (under Past events, the event being over), emails the placed leads their place, and owes the winner,
runner-up and third-place certificates. Publishing waits for the final, and only
someone who may publish the event's results can.
"""
import pytest

import services_certificates as certs
import services_sports as sports
from tests.test_integration_flow import _login, _unique, _user
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401

TEAMS = [{'id': f't{i}', 'name': f'Team {c}'} for i, c in enumerate('ABCDEFGH', start=1)]


def _settle(t, round_winner='home', third_winner='home'):
    """Play every match round by round: the home side (or the away side) wins."""
    for rnd in sorted({m['round'] for m in t['matches']}):
        for m in [m for m in t['matches'] if m['round'] == rnd and m['status'] == 'scheduled']:
            side = third_winner if m.get('stage') == 'third' else round_winner
            t = sports.record_result(t, m['id'], 3 if side == 'home' else 1, 1 if side == 'home' else 3)
    return t


def _by_stage(t, stage):
    return [m for m in t['matches'] if m.get('stage') == stage]


def test_placings_for_a_knockout_with_and_without_a_third_place_match_and_a_league():
    # Without a third-place match: both losing semi-finalists are third
    t = sports.generate(TEAMS, 'knockout')
    assert sports.placings(t) == {}                                   # nothing played
    semis = _by_stage(t, 'semi')
    assert len(semis) == 2 and len(_by_stage(t, 'final')) == 1 and not _by_stage(t, 'third')
    t = _settle(t)
    # Home wins every match: A beats B, C beats D, … ; semis A v C and E v G; final A v E
    assert sports.placings(t) == {'t1': 1, 't5': 2, 't3': 3, 't7': 3}

    # With one: its winner alone is third, and nothing is placed until it's played
    t = sports.generate(TEAMS, 'knockout', third_place=True)
    assert len(t['matches']) == 8
    third = _by_stage(t, 'third')[0]
    for rnd in (1, 2, 3):
        for m in [m for m in t['matches'] if m['round'] == rnd and m.get('stage') != 'third']:
            t = sports.record_result(t, m['id'], 2, 0)
    third = [m for m in t['matches'] if m['id'] == third['id']][0]
    assert (third['home'], third['away']) == ('t3', 't7')            # the semi-finals' losers
    assert sports.placings(t) == {}                                   # the final alone isn't enough
    t = sports.record_result(t, third['id'], 1, 4)
    assert sports.placings(t) == {'t1': 1, 't5': 2, 't7': 3}

    # A league: the top three once every match is played
    t = sports.generate(TEAMS[:4], 'league')
    t = sports.record_result(t, t['matches'][0]['id'], 1, 0)
    assert sports.placings(t) == {}
    for m in t['matches'][1:]:
        t = sports.record_result(t, m['id'], 1, 0)
    top = [row['id'] for row in sports.standings(t)[:3]]
    assert sports.placings(t) == {top[0]: 1, top[1]: 2, top[2]: 3}

    # Three teams can't have a third-place match
    with pytest.raises(sports.TournamentError, match='at least 4 teams'):
        sports.generate(TEAMS[:3], 'knockout', third_place=True)


def _knockout_with_a_student_lead(d, monkeypatch):
    """A four-team knockout whose first team's lead is a student who can log in."""
    event_id, ids = d['event'](['Lions', 'Tigers', 'Bears', 'Wolves'])
    lead = f"{_unique('lionlead')}@test.edu"
    _user(d['db'], lead, 'Student', name='Leo Lead')
    d['db'].collection('registrations').document(ids['Lions']).update({'lead_email': lead, 'lead_name': 'Leo Lead'})
    sent = []
    monkeypatch.setattr('utils_email.send_result_email',
                        lambda to, name, title, rank, score: sent.append((to, rank, score)) or True)
    return event_id, ids, lead, sent


def test_publishing_from_the_tournament_page_makes_the_places_the_result(cup, monkeypatch):  # noqa: F811
    d = cup
    event_id, ids, lead, sent = _knockout_with_a_student_lead(d, monkeypatch)
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    t = _t(d, event_id)
    for rnd in (1, 2):
        for m in [m for m in _t(d, event_id)['matches'] if m['round'] == rnd]:
            winner_is_home = names_of(d, event_id, m['home']) in ('Lions', 'Bears')
            _play(d['owner'], event_id, m, 5 if winner_is_home else 2, 2 if winner_is_home else 5)
    t = _t(d, event_id)
    assert sports.placings(t)[ids['Lions']] == 1

    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-tournament-result' in page and 'Publish results' in page
    assert d['owner'].post(f'/tournament/{event_id}/publish').status_code == 302

    regs = {r.id: r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()}
    places = {r['team_name']: r.get('final_rank') for r in regs.values() if r.get('status') == 'Confirmed'}
    loser_semi = [n for n in ('Tigers', 'Wolves') if places[n] == 3]
    assert places['Lions'] == 1 and places['Bears'] == 2 and len(loser_semi) == 2
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert event['results_published'] and event['status'] == 'completed'
    assert [w['rank'] for w in event['winners']] == [1, 2, 3, 3]
    assert sorted(rank for _, rank, _ in sent) == [1, 2, 3, 3] and all(score is None for *_, score in sent)
    assert (lead, 1, None) in sent

    student = _login(d['app'], lead, 'Student')
    dash = student.get('/participant/dashboard').get_data(as_text=True)
    card = dash[dash.index('<div class="past-card__title">'):]        # completed, so under Past events
    assert 'Rank #1' in card[:card.index('</div>', card.index('<div class="past-card__meta">'))]

    owed = {(r['team'], r['cert_type']) for r in certs.recipients(d['db'], event_id)
            if r['cert_type'] in certs.POSITION_TYPES}
    assert owed == {('Lions', 'winner'), ('Bears', 'runner_up'), ('Tigers', 'position'), ('Wolves', 'position')}
    assert 'Published' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)


def names_of(d, event_id, team_id):
    return sports.names(_t(d, event_id)).get(team_id)


def test_publishing_waits_for_the_final_and_needs_the_right_to_publish(cup, monkeypatch):  # noqa: F811
    d = cup
    event_id, ids, lead, sent = _knockout_with_a_student_lead(d, monkeypatch)
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout', 'third_place': 'yes'})
    t = _t(d, event_id)
    assert len(t['matches']) == 4 and _by_stage(t, 'third')
    for m in [m for m in t['matches'] if m['round'] == 1]:
        _play(d['owner'], event_id, m, 3, 1)

    d['owner'].post(f'/tournament/{event_id}/publish')                 # the final isn't played
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert not event.get('results_published') and not sent
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Publish results' not in page and 'the final (and any third-place match) is played' in page

    for m in [m for m in _t(d, event_id)['matches'] if m['round'] == 2]:
        _play(d['owner'], event_id, m, 3, 1)
    # A student or a SPOC from elsewhere can't publish; the event's coordinator scores but doesn't publish
    student = _login(d['app'], lead, 'Student')
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    for client in (student, _login(d['app'], other, 'ClubSPOC')):
        assert client.post(f'/tournament/{event_id}/publish').status_code == 403
    assert not d['db'].collection('events').document(event_id).get().to_dict().get('results_published')

    # The SPOC's generic Publish does the same for a tournament
    d['owner'].post(f'/spoc/publish_results/{event_id}')
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert event.get('results_published') and [w['rank'] for w in event['winners']] == [1, 2, 3]
