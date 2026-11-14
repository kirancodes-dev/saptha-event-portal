"""
tests/test_window_summary.py — UPG-252 on the real database layer, with a
mail provider configured (UPG-207's fixture).

A member added, or joining with the invite code, while the SPOC's window
(UPG-250) is open is marked: the SPOC's list labels them "Added during
window" with when and by whom, and filters on them. One added before the
deadline isn't. When the window ends, by "Close now" or by its time passing
(seen by the hourly job or the SPOC's next visit), the SPOC gets one portal
notice naming the members added and whether each confirmed.
"""
import datetime
import html

import services_team_confirm as confirm
import services_team_members as tm
from tests import test_team_member_confirm as _tc
from tests.test_team_add_members_window import _add, _close_registration, _event, _notices, _open, _student
from tests.test_team_member_confirm import _flashes

team = _tc.team   # UPG-207's fixture


def _list(t, event_id, query=''):
    return html.unescape(t['owner'].get(f'/coordinator/registrations/{event_id}{query}').get_data(as_text=True))


def _summaries(t):
    return _notices(t, t['spoc'], kind='team_window_closed')


# ── Criterion 1: labelled and filtered; one added before the deadline isn't ─

def test_a_member_added_in_the_window_is_labelled_and_filtered_one_added_before_isnt(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1), team_name='Early Team')
    lead2, reg2 = t['register'](event_id, mates=t['mates'](1), team_name='Joined Team')
    code2 = t['reg'](reg2)['team_code']
    t['register'](event_id, mates=t['mates'](1), team_name='Untouched Team')
    client = t['lead_client'](lead)

    _add(client, reg_id, _unique_email('before'), name='Bea Before')     # registration still open
    assert not any(m.get('late') for m in t['reg'](reg_id)['members'])
    page = _list(t, event_id)
    assert 'Added during window' not in page and 'members=late' not in page

    _close_registration(t, event_id)
    _open(t['owner'], event_id, '60')
    _add(client, reg_id, _unique_email('late'), name='Lee Late')
    joiner, joiner_client = _student(t)
    joiner_client.post('/teams/join', data={'join_code': code2})
    assert 'You joined Joined Team.' in _flashes(joiner_client)

    late = {m['name'] or m['email'] for m in t['reg'](reg_id)['members'] if m.get('late')}
    assert late == {'Lee Late'}
    [joined] = [m for m in t['reg'](reg2)['members'] if m.get('email') == joiner]
    assert joined['late'] and joined['added_by'] == joiner

    page = _list(t, event_id)
    assert page.count('data-late') == 2
    assert f'by {lead}' in page and 'Added ' in page
    assert 'members=late' in page and 'added during window' in page

    # The filter: both teams with a late member, not the team without one
    assert 'Untouched Team' in page
    shown = _list(t, event_id, '?members=late')
    assert 'Early Team' in shown and 'Joined Team' in shown and 'Untouched Team' not in shown


# ── Criterion 2: one notice to the SPOC when it closes ──────────────────────

def test_close_now_sends_the_spoc_one_notice_naming_the_members_added(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1), team_name='Byte Force')
    _close_registration(t, event_id)
    _open(t['owner'], event_id, '60')
    client = t['lead_client'](lead)
    first, second = _unique_email('one'), _unique_email('two')
    _add(client, reg_id, first, name='Nia One')
    _add(client, reg_id, second, name='Omar Two')
    confirm.confirm(t['db'], reg_id, first, 'link')

    t['owner'].post(f'/coordinator/registrations/{event_id}/add_members_window', data={'action': 'close'})
    assert "Closed: teams can't change any more. 2 members added" in _flashes(t['owner'])
    [notice] = _summaries(t)
    assert '2 members added' in notice['title']
    assert 'Nia One (Byte Force): confirmed' in notice['message']
    assert 'Omar Two (Byte Force): not confirmed yet' in notice['message']
    assert notice['link'] == f'/coordinator/registrations/{event_id}?members=late'

    # Nothing more on a second close, or the next visit
    t['owner'].post(f'/coordinator/registrations/{event_id}/add_members_window', data={'action': 'close'})
    _list(t, event_id)
    assert len(_summaries(t)) == 1


def test_a_window_that_runs_out_is_summed_up_once_by_the_job_or_the_next_visit(team, monkeypatch):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1), team_name='Timed Team')
    _close_registration(t, event_id)
    _open(t['owner'], event_id, '30')
    _add(t['lead_client'](lead), reg_id, _unique_email('timed'), name='Tia Timed')

    later = tm._now() + datetime.timedelta(minutes=31)
    real = tm._now   # put back by hand: undoing all would also undo real_app's db
    monkeypatch.setattr(tm, '_now', lambda: later)
    assert tm.finish_ended_windows(t['db']) >= 1                       # the hourly job
    [notice] = _summaries(t)
    assert '1 member added' in notice['title'] and 'Tia Timed (Timed Team)' in notice['message']
    tm.finish_ended_windows(t['db'])                                   # the next hour: nothing new
    assert len(_summaries(t)) == 1
    _list(t, event_id)
    assert len(_summaries(t)) == 1
    assert not _event(t, event_id).get(tm.WINDOW)

    # A second window: the job didn't run, the SPOC's visit ends it; only its own member is named
    monkeypatch.setattr(tm, '_now', real)
    _open(t['owner'], event_id, '30')
    _add(t['lead_client'](lead), reg_id, _unique_email('second'), name='Sid Second')
    later = tm._now() + datetime.timedelta(minutes=31)
    monkeypatch.setattr(tm, '_now', lambda: later)
    _list(t, event_id)
    summaries = _summaries(t)
    assert len(summaries) == 2
    newest = next(n for n in summaries if 'Sid Second' in n['message'])
    assert 'Tia Timed' not in newest['message'] and '1 member added' in newest['title']


def _unique_email(prefix):
    from tests.test_integration_flow import _unique
    return f"{_unique(prefix)}@test.edu"
