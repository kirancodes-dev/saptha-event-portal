"""
tests/test_tournament_fixes.py — every tournament mistake is fixed from the
page, without code (UPG-353 to UPG-359):

- UPG-353: the staff page's scores can be read (a dark badge, not white on white).
- UPG-354: two changes saved at the same moment both stay; the lock is shared
  by every copy of the app, and a dead holder's lock is taken over.
- UPG-355: a result is cleared (a knockout's winner comes back out of the next
  match); a correction past a played match says which one to clear; a match
  ended live by mistake is reopened; any point in the live log is removed.
- UPG-356: a walkover, and a team withdrawn (its matches still to play become
  walkovers, a knockout's next rounds too) and brought back.
- UPG-357: a team renamed, replaced by another registration, a late team added
  to a league, a match's teams changed (a playoff seeding by toss).
- UPG-358: the points rule changed without making the fixtures again; the
  playoffs undone.
- UPG-359: corrected results published again: only the teams whose place
  changed are told, and the certificates for the old places are revoked.
"""
import re
import threading
import time

import pytest

import services_certificates as certs
import services_live_match as live
import services_sports as sports
from tests.test_integration_flow import _login, _unique, _user
from tests.test_live_match import _tap
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401

TEAMS = [{'id': f't{i}', 'name': f'Team {c}'} for i, c in enumerate('ABCD', start=1)]


def _m(t, mid):
    return next(m for m in t['matches'] if m['id'] == mid)


def _stage(t, stage):
    return [m for m in t['matches'] if m.get('stage') == stage]


# ── UPG-353 ───────────────────────────────────────────────────────────────
def test_the_staff_page_scores_can_be_read(cup):  # noqa: F811
    d = cup
    event_id, _ = d['event'](['Ants', 'Bees'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    _play(d['owner'], event_id, _t(d, event_id)['matches'][0], 31, 27)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    badges = re.findall(r'<span class="([^"]*)" data-score-badge>([^<]*)</span>', page)
    assert badges == [('badge bg-dark fs-6', '31'), ('badge bg-dark fs-6', '27')]
    assert 'class="badge fs-6"' not in page


# ── UPG-354 ───────────────────────────────────────────────────────────────
def test_two_results_saved_at_the_same_moment_both_stay(cup):  # noqa: F811
    d = cup
    event_id, _ = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    first, second = _t(d, event_id)['matches'][:2]
    start = threading.Barrier(2)
    errors = []

    def court(m, home, away):
        def slow(cur, _event):
            time.sleep(0.3)                     # both have read the tournament before either writes
            return sports.record_result(cur, m['id'], home, away)
        try:
            start.wait()
            sports.change(d['db'], event_id, slow)
        except Exception as exc:                # pragma: no cover - shown by the assert
            errors.append(exc)

    threads = [threading.Thread(target=court, args=(first, 30, 20)),
               threading.Thread(target=court, args=(second, 25, 26))]
    [x.start() for x in threads]
    [x.join() for x in threads]
    assert not errors
    t = _t(d, event_id)
    assert (_m(t, first['id'])['home_score'], _m(t, second['id'])['away_score']) == (30, 26)
    assert _m(t, first['id'])['status'] == _m(t, second['id'])['status'] == 'played'


def test_the_lock_is_shared_and_a_dead_holders_lock_is_taken_over(cup, monkeypatch):  # noqa: F811
    from db_pg import get_session
    from models_pg import TicketTypeSale
    d = cup
    event_id, _ = d['event'](['Ants', 'Bees'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    key = f"{event_id}:tournament-lock"
    monkeypatch.setattr(sports, 'LOCK_WAIT', 0.3)

    def held_since(seconds_ago):
        with get_session(primary=True) as s:
            row = s.get(TicketTypeSale, key)
            row.sold = int(time.time()) - seconds_ago

    held_since(0)                                # another copy of the app is saving right now
    with pytest.raises(sports.TournamentError, match='Someone else is saving'):
        sports.change(d['db'], event_id, lambda cur, _e: cur)
    resp = d['owner'].post(f"/tournament/{event_id}/match/{_t(d, event_id)['matches'][0]['id']}/result",
                           data={'home_score': '3', 'away_score': '1'}, follow_redirects=True)
    assert 'Someone else is saving' in resp.get_data(as_text=True)
    assert _t(d, event_id)['matches'][0]['status'] == 'scheduled'

    held_since(sports.LOCK_SECONDS + 5)          # that copy died holding it
    m = _t(d, event_id)['matches'][0]
    sports.change(d['db'], event_id, lambda cur, _e: sports.record_result(cur, m['id'], 3, 1))
    assert _t(d, event_id)['matches'][0]['status'] == 'played'
    with get_session(primary=True) as s:
        assert s.get(TicketTypeSale, key).sold == 0          # let go after the change


# ── UPG-355 ───────────────────────────────────────────────────────────────
def test_a_result_is_cleared_and_the_winner_comes_back_out_of_the_next_match():
    t = sports.generate(TEAMS, 'knockout', third_place=True)
    semi1, semi2 = _stage(t, 'semi')
    final, third = _stage(t, 'final')[0], _stage(t, 'third')[0]
    t = sports.record_result(t, semi1['id'], 30, 20)
    assert _m(t, final['id'])['home'] == 't1' and _m(t, third['id'])['home'] == 't2'
    t = sports.clear_result(t, semi1['id'])
    assert _m(t, semi1['id'])['status'] == 'scheduled' and _m(t, semi1['id'])['winner'] is None
    assert _m(t, final['id'])['home'] is None and _m(t, third['id'])['home'] is None

    t = sports.record_result(t, semi1['id'], 30, 20)
    t = sports.record_result(t, semi2['id'], 30, 20)
    t = sports.record_result(t, final['id'], 40, 35)
    with pytest.raises(sports.TournamentError, match=r'Final \(match M\d\) is already played'):
        sports.record_result(t, semi1['id'], 20, 30)          # the other team went through: clear the final first
    with pytest.raises(sports.TournamentError, match='Clear that result first'):
        sports.clear_result(t, semi1['id'])
    t = sports.record_result(t, semi1['id'], 31, 20)          # the same team goes through: fine
    t = sports.clear_result(t, final['id'])
    t = sports.record_result(t, semi1['id'], 20, 30)          # now the correction is allowed
    assert _m(t, final['id'])['home'] == 't2' and _m(t, third['id'])['home'] == 't1'
    with pytest.raises(sports.TournamentError, match='no result'):
        sports.clear_result(t, final['id'])


def test_clearing_on_the_page_and_reopening_a_match_ended_live_by_mistake(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['db'].collection('events').document(event_id).update({'details': {'sport': 'Kabaddi'}})
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    m = [x for x in _t(d, event_id)['matches'] if x['round'] == 1][0]
    d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    for body in ({'op': 'phase', 'action': 'start'},
                 {'op': 'point', 'team': 'home', 'kind': 'raid', 'points': 3},
                 {'op': 'point', 'team': 'away', 'kind': 'tackle'},     # meant for home
                 {'op': 'point', 'team': 'home', 'kind': 'bonus'},
                 {'op': 'phase', 'action': 'half_time'}, {'op': 'phase', 'action': 'second_half'},
                 {'op': 'phase', 'action': 'full_time'}):
        status, data = _tap(d['coord'], event_id, m['id'], **body)
        assert status == 200, data
    assert _m(_t(d, event_id), m['id'])['status'] == 'played'

    # Full time was too early: reopen; the result comes off the fixtures, the 2nd half goes on
    status, data = _tap(d['coord'], event_id, m['id'], op='reopen')
    assert status == 200 and data['state']['phase'] == 'second_half' and not data['state']['running']
    after = _t(d, event_id)
    assert _m(after, m['id'])['status'] == 'scheduled' and not _m(after, m['id']).get('winner')
    assert all(x['home'] is None for x in after['matches'] if x.get('stage') == 'final')
    # Any point, not just the last, can be taken back
    wrong = [e for e in data['entries'] if 'Tackle' in e['text']][0]
    status, data = _tap(d['coord'], event_id, m['id'], op='remove', entry=wrong['id'])
    assert status == 200 and (data['state']['home']['total'], data['state']['away']['total']) == (4, 0)
    assert len(data['entries']) == 2
    _tap(d['coord'], event_id, m['id'], op='point', team='home', kind='tackle')
    _tap(d['coord'], event_id, m['id'], op='phase', action='full_time')
    played = _m(_t(d, event_id), m['id'])
    assert (played['home_score'], played['away_score'], played['winner']) == (5, 0, m['home'])
    assert _tap(d['coord'], event_id, m['id'], op='remove', entry=data['entries'][0]['id'])[0] == 409

    # Clearing on the tournament page reopens the live match too; a stranger can't clear
    stranger = f"{_unique('nosy')}@test.edu"
    _user(d['db'], stranger, 'Student')
    assert _login(d['app'], stranger, 'Student').post(
        f"/tournament/{event_id}/match/{m['id']}/clear").status_code == 403
    page = d['coord'].post(f"/tournament/{event_id}/match/{m['id']}/clear", follow_redirects=True)
    assert 'Result cleared' in page.get_data(as_text=True)
    assert live.get(d['db'], event_id, m['id'])['phase'] == 'second_half'
    scorer = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-reopen' in scorer and 'All points (3)' in scorer and scorer.count('data-remove=') == 3


# ── UPG-356 ───────────────────────────────────────────────────────────────
def test_a_walkover_and_a_withdrawn_team_in_a_league():
    t = sports.generate(TEAMS, 'league', points=sports.KABADDI_POINTS, sport='Kabaddi')
    ab = next(m for m in t['matches'] if {m['home'], m['away']} == {'t1', 't2'})
    t = sports.walkover(t, ab['id'], 't2')
    row = {r['id']: r for r in sports.standings(t)}
    assert (row['t2']['won'], row['t2']['points'], row['t2']['for']) == (1, 5, 0)
    assert (row['t1']['lost'], row['t1']['points']) == (1, 0)        # no close-loss point for a no-show
    with pytest.raises(sports.TournamentError, match='Choose the team'):
        sports.walkover(t, ab['id'], 't9')

    cd = next(m for m in t['matches'] if {m['home'], m['away']} == {'t3', 't4'})
    t = sports.record_result(t, cd['id'], 30, 29)
    t = sports.withdraw(t, 't3')                                     # Team C pulls out
    for m in t['matches']:
        if 't3' in (m['home'], m['away']) and m['id'] != cd['id']:
            assert m['walkover'] and m['winner'] != 't3' and m['status'] == 'played'
    assert _m(t, cd['id'])['home_score'] == 30 and not _m(t, cd['id']).get('walkover')   # played results stay
    assert sports.withdrawn(t) == {'t3'}
    t = sports.reinstate(t, 't3')
    assert sports.withdrawn(t) == set()
    with pytest.raises(sports.TournamentError, match="hasn't withdrawn"):
        sports.reinstate(t, 't3')
    # A real result over a walkover takes the walkover off
    t = sports.clear_result(t, ab['id'])
    t = sports.record_result(t, ab['id'], 20, 18)
    assert not _m(t, ab['id']).get('walkover')


def test_a_team_withdrawn_from_a_knockout_and_walkovers_on_the_pages(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    semi1, semi2 = [m for m in _t(d, event_id)['matches'] if m['round'] == 1]
    _play(d['coord'], event_id, semi1, 30, 20)                # the home team reaches the final
    winner = semi1['home']
    # The winner pulls out before the final: whoever comes through the other semi gets it by walkover
    d['owner'].post(f'/tournament/{event_id}/team/{winner}/withdraw')
    _play(d['coord'], event_id, semi2, 10, 25)
    t = _t(d, event_id)
    final = _stage(t, 'final')[0]
    assert final['walkover'] and final['winner'] == semi2['away'] and sports.champion(t) == semi2['away']
    assert sports.placings(t) == {semi2['away']: 1, winner: 2, semi1['away']: 3, semi2['home']: 3}
    staff = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Withdrawn</span>' in staff and 'W/O' in staff
    public = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'W/O' in public
    # A walkover by hand needs both teams; a coordinator can give one; withdrawing is the SPOC's
    assert d['coord'].post(f'/tournament/{event_id}/team/{semi2["home"]}/withdraw').status_code == 403


# ── UPG-357 ───────────────────────────────────────────────────────────────
def test_teams_renamed_replaced_added_and_a_matchs_teams_changed(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    t = _t(d, event_id)
    ab = next(m for m in t['matches'] if {m['home'], m['away']} == {ids['Ants'], ids['Bees']})
    _play(d['owner'], event_id, ab, 30, 20)

    d['owner'].post(f"/tournament/{event_id}/team/{ids['Ants']}/rename", data={'name': 'Ants United'})
    assert 'Ants United' in d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)

    # Two late registrations: one takes Bees' place (results included), one joins the league
    late = {}
    for name in ('Owls', 'Yaks'):
        late[name] = _unique('REG')
        d['db'].collection('registrations').document(late[name]).set({
            'event_id': event_id, 'team_name': name, 'lead_name': f'{name} lead', 'status': 'Confirmed',
            'lead_email': f"{_unique('cap')}@test.edu", 'registered_at': '2026-10-02 10:00:00'})
    late = {r.to_dict()['team_name']: r.id
            for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()
            if r.to_dict()['team_name'] in ('Owls', 'Yaks')}
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-teams' in page and 'Add a late team' in page and '>Owls</option>' in page
    d['owner'].post(f"/tournament/{event_id}/team/{ids['Bees']}/replace", data={'new_team': late['Owls']})
    t = _t(d, event_id)
    assert ids['Bees'] not in sports.names(t) and sports.names(t)[late['Owls']] == 'Owls'
    played = _m(t, ab['id'])
    assert late['Owls'] in (played['home'], played['away']) and played['status'] == 'played'
    before = len(t['matches'])
    d['owner'].post(f'/tournament/{event_id}/teams/add', data={'new_team': late['Yaks']})
    t = _t(d, event_id)
    assert len(t['matches']) == before + 3
    assert sum(late['Yaks'] in (m['home'], m['away']) for m in t['matches']) == 3
    assert len({m['id'] for m in t['matches']}) == len(t['matches'])
    with pytest.raises(sports.TournamentError, match='knockout'):
        sports.add_team(sports.generate(TEAMS, 'knockout'), {'id': 'x', 'name': 'X'})

    # A match not yet played gets other teams; a played one must be cleared first
    open_match = next(m for m in t['matches'] if m['status'] == 'scheduled')
    d['owner'].post(f"/tournament/{event_id}/match/{open_match['id']}/teams",
                    data={'home': late['Yaks'], 'away': ids['Cats']})
    assert (_m(_t(d, event_id), open_match['id'])['home'], _m(_t(d, event_id), open_match['id'])['away']) == \
        (late['Yaks'], ids['Cats'])
    with pytest.raises(sports.TournamentError, match='Clear'):
        sports.set_match_teams(_t(d, event_id), ab['id'], ids['Cats'], late['Yaks'])
    with pytest.raises(sports.TournamentError, match="can't play itself"):
        sports.set_match_teams(_t(d, event_id), open_match['id'], ids['Cats'], ids['Cats'])
    assert d['coord'].post(f"/tournament/{event_id}/team/{ids['Cats']}/rename",
                           data={'name': 'X'}).status_code == 403


def test_a_playoff_seeding_by_toss_and_a_match_with_live_points_keeps_its_teams(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league_knockout'})
    for m in _t(d, event_id)['matches']:
        _play(d['owner'], event_id, m, 20, 20)                 # all tied: the order is by name
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'})
    semi1, semi2 = _stage(_t(d, event_id), 'semi')
    assert (semi1['home'], semi1['away'], semi2['home'], semi2['away']) == \
        (ids['Ants'], ids['Dogs'], ids['Bees'], ids['Cats'])
    # A toss says Cats, not Dogs, play Ants: one team can't be in both semis, so it goes through TBD
    resp = d['owner'].post(f"/tournament/{event_id}/match/{semi1['id']}/teams",
                           data={'home': ids['Ants'], 'away': ids['Cats']}, follow_redirects=True)
    assert f"Cats already plays in match {semi2['id'].upper()}" in resp.get_data(as_text=True)
    d['owner'].post(f"/tournament/{event_id}/match/{semi2['id']}/teams", data={'home': ids['Bees'], 'away': ''})
    d['owner'].post(f"/tournament/{event_id}/match/{semi1['id']}/teams", data={'home': ids['Ants'], 'away': ids['Cats']})
    d['owner'].post(f"/tournament/{event_id}/match/{semi2['id']}/teams", data={'home': ids['Bees'], 'away': ids['Dogs']})
    t = _t(d, event_id)
    assert (_m(t, semi1['id'])['away'], _m(t, semi2['id'])['away']) == (ids['Cats'], ids['Dogs'])
    assert t['playoffs']['seeds'] == [ids['Ants'], ids['Cats'], ids['Bees'], ids['Dogs']]
    semi1 = _m(t, semi1['id'])

    d['owner'].get(f"/tournament/{event_id}/match/{semi1['id']}/score")
    _tap(d['owner'], event_id, semi1['id'], op='phase', action='start')
    _tap(d['owner'], event_id, semi1['id'], op='point', team='home', kind='score', points=2)
    resp = d['owner'].post(f"/tournament/{event_id}/match/{semi1['id']}/teams",
                           data={'home': ids['Cats'], 'away': ids['Ants']}, follow_redirects=True)
    assert 'being scored live' in resp.get_data(as_text=True)
    assert _m(_t(d, event_id), semi1['id'])['home'] == ids['Ants']


# ── UPG-358 ───────────────────────────────────────────────────────────────
def test_the_points_rule_changes_and_the_playoffs_are_undone(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league_knockout'})
    name = {v: k for k, v in ids.items()}
    for m in _t(d, event_id)['matches']:
        home, away = name[m['home']], name[m['away']]
        _play(d['owner'], event_id, m, 30 if home < away else 27, 27 if home < away else 30)   # earlier name wins by 3
    assert {r['name']: r['points'] for r in sports.standings(_t(d, event_id))}['Dogs'] == 0
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Change the points rule' in page
    d['owner'].post(f'/tournament/{event_id}/points', data={
        'points_win': '5', 'points_draw': '3', 'points_loss': '0', 'points_close_loss': '1', 'points_close_margin': '7'})
    table = {r['name']: r['points'] for r in sports.standings(_t(d, event_id))}
    assert table == {'Ants': 15, 'Bees': 11, 'Cats': 7, 'Dogs': 3}       # a close loss now earns 1

    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4', 'third_place': 'yes'})
    t = _t(d, event_id)
    assert len(sports.playoff_ids(t)) == 4
    with pytest.raises(sports.TournamentError, match='Undo the playoffs'):
        sports.set_points(t, sports.DEFAULT_POINTS)
    semi = _stage(t, 'semi')[0]
    d['owner'].get(f"/tournament/{event_id}/match/{semi['id']}/score")       # a live record for a playoff
    assert live.get(d['db'], event_id, semi['id'])
    _play(d['owner'], event_id, semi, 30, 10)
    assert 'data-undo-playoffs' not in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    resp = d['owner'].post(f'/tournament/{event_id}/playoffs/undo', follow_redirects=True)
    assert 'Clear the playoff results first' in resp.get_data(as_text=True)
    d['owner'].post(f"/tournament/{event_id}/match/{semi['id']}/clear")
    assert 'data-undo-playoffs' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert d['coord'].post(f'/tournament/{event_id}/playoffs/undo').status_code == 403
    d['owner'].post(f'/tournament/{event_id}/playoffs/undo')
    t = _t(d, event_id)
    assert not sports.has_playoffs(t) and 'playoffs' not in t and len(t['matches']) == 6
    assert live.get(d['db'], event_id, semi['id']) is None                 # its live record went with it
    # Now a league result can be corrected, and the playoffs made again
    first = t['matches'][0]
    _play(d['owner'], event_id, first, 1, 40)
    assert _m(_t(d, event_id), first['id'])['away_score'] == 40
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '2'})
    assert len(_stage(_t(d, event_id), 'final')) == 1


def test_making_the_fixtures_again_forgets_the_old_live_records(cup):  # noqa: F811
    d = cup
    event_id, _ = d['event'](['Ants', 'Bees'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    m = _t(d, event_id)['matches'][0]
    d['owner'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    assert live.get(d['db'], event_id, m['id'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league', 'confirm_replace': 'yes'})
    assert live.get(d['db'], event_id, m['id']) is None


# ── UPG-359 ───────────────────────────────────────────────────────────────
def test_corrected_results_are_published_again(cup, monkeypatch):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees'])
    sent = []
    monkeypatch.setattr('utils_email.send_result_email',
                        lambda to, name, title, rank, score: sent.append((name, rank)) or True)
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    final = _t(d, event_id)['matches'][0]
    _play(d['owner'], event_id, final, 30, 20)
    d['owner'].post(f'/tournament/{event_id}/publish')
    home, away = final['home'], final['away']
    lead = {ids['Ants']: 'Ants lead', ids['Bees']: 'Bees lead'}
    assert sorted(sent) == sorted([(lead[home], 1), (lead[away], 2)])
    # The winner's certificate was issued
    regs = {r.id: r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()}
    issued = certs.claim(event_id, {'person_key': certs.person_key(email=regs[home]['lead_email']),
                                    'email': regs[home]['lead_email'], 'name': lead[home], 'reg_id': home,
                                    'cert_type': 'winner', 'position': 1}, {})
    assert issued

    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-results-changed' not in page and 'publish again' in page
    # The score was the other way round
    sent.clear()
    d['owner'].post(f"/tournament/{event_id}/match/{final['id']}/result", data={'home_score': '20', 'away_score': '30'})
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-results-changed' in page and 'Publish the corrected results' in page
    resp = d['owner'].post(f'/tournament/{event_id}/publish', follow_redirects=True).get_data(as_text=True)
    assert 'Corrected results published' in resp and '2 teams told their new place' in resp
    assert '1 position certificate for the old places revoked' in resp
    regs = {r.id: r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()}
    assert (regs[away]['final_rank'], regs[home]['final_rank']) == (1, 2)
    assert sorted(sent) == sorted([(lead[away], 1), (lead[home], 2)])
    assert certs.by_number(issued['number'])['status'] == 'revoked'
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert [w['rank'] for w in event['winners']] == [1, 2] and 'reg_id' not in event['winners'][0]

    # Pressed again with nothing changed: nobody is told anything
    sent.clear()
    resp = d['owner'].post(f'/tournament/{event_id}/publish', follow_redirects=True).get_data(as_text=True)
    assert 'already match' in resp and not sent


def test_a_coordinator_gives_a_walkover_and_the_super_admin_fixes_everything(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Ants', 'Bees', 'Cats'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    first = _t(d, event_id)['matches'][0]
    page = d['coord'].post(f"/tournament/{event_id}/match/{first['id']}/walkover",
                           data={'winner': first['away']}, follow_redirects=True).get_data(as_text=True)
    assert 'Walkover' in page
    assert _m(_t(d, event_id), first['id'])['walkover'] and _m(_t(d, event_id), first['id'])['winner'] == first['away']

    admin = f"{_unique('root')}@test.edu"
    _user(d['db'], admin, 'SuperAdmin')
    root = _login(d['app'], admin, 'SuperAdmin')
    assert root.get(f'/tournament/{event_id}').status_code == 200
    root.post(f"/tournament/{event_id}/match/{first['id']}/clear")
    assert _m(_t(d, event_id), first['id'])['status'] == 'scheduled'
    root.post(f"/tournament/{event_id}/team/{ids['Cats']}/rename", data={'name': 'Cats FC'})
    root.post(f"/tournament/{event_id}/team/{ids['Bees']}/withdraw")
    root.post(f'/tournament/{event_id}/points', data={'points_win': '3', 'points_draw': '1', 'points_loss': '0'})
    t = _t(d, event_id)
    assert sports.names(t)[ids['Cats']] == 'Cats FC' and sports.withdrawn(t) == {ids['Bees']}
    assert t['points']['win'] == 3
    assert all(m['walkover'] for m in t['matches'] if ids['Bees'] in (m['home'], m['away']))
    assert not any(m.get('walkover') for m in t['matches'] if ids['Bees'] not in (m['home'], m['away']))
