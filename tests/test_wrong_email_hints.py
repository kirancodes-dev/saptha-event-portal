"""
tests/test_wrong_email_hints.py — UPG-257 on the real database layer, with a
mail provider configured (UPG-207's fixture).

A teammate who hasn't confirmed may have been given a mistyped email. The
lead's team page asks about it next to that member, with the form to correct
it in view; the lead's dashboard reminds them how many haven't confirmed; and
the event's SPOC can list only the teams with a member who hasn't confirmed.
"""
import services_team_confirm as confirm
from tests import test_team_member_confirm as _tc

team = _tc.team   # UPG-207's fixture


def _team_with_one_confirmed(t, event_id, team_name='Byte Force'):
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates=mates, team_name=team_name)
    confirm.confirm(t['db'], reg_id, mates[0], 'link')
    return lead, reg_id, mates


# ── Criterion 1: the team page and the lead's dashboard ─────────────────────

def test_the_team_page_asks_about_an_unconfirmed_member_only_and_the_dashboard_counts_them(team):
    t = team
    event_id = t['event']()
    lead, reg_id, mates = _team_with_one_confirmed(t, event_id)
    client = t['lead_client'](lead)

    page = client.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert page.count('data-wrong-email') == 1
    assert "Mate 2 hasn't confirmed yet. Wrong email?" in page
    assert "Mate 1 hasn't confirmed" not in page
    assert 'Correct the email and send a new link' in page

    dash = client.get('/participant/dashboard').get_data(as_text=True)
    assert 'data-unconfirmed-reminder' in dash
    import html
    text = html.unescape(dash)
    assert "1 teammate on Byte Force" in text and "hasn't confirmed: Mate 2" in text
    assert f'href="/teams/{reg_id}"' in dash

    # Everyone confirmed: no prompt, no reminder
    confirm.confirm(t['db'], reg_id, mates[1], 'link')
    assert 'data-wrong-email' not in client.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-unconfirmed-reminder' not in client.get('/participant/dashboard').get_data(as_text=True)


def test_the_reminder_is_not_shown_when_the_organiser_switched_confirming_off(team):
    t = team
    event_id = t['event'](member_confirm=False)
    lead, _, _ = _team_with_one_confirmed(t, event_id)
    dash = t['lead_client'](lead).get('/participant/dashboard').get_data(as_text=True)
    assert 'data-unconfirmed-reminder' not in dash


# ── Criterion 2: the SPOC's filter ──────────────────────────────────────────

def test_the_spocs_filter_lists_only_teams_with_an_unconfirmed_member(team):
    t = team
    event_id = t['event']()
    _, waiting_reg, _ = _team_with_one_confirmed(t, event_id, team_name='Waiting Team')
    _, done_reg, done = _team_with_one_confirmed(t, event_id, team_name='Done Team')
    confirm.confirm(t['db'], done_reg, done[1], 'link')

    everyone = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'Waiting Team' in everyone and 'Done Team' in everyone
    assert 'members=unconfirmed' in everyone and 'members not confirmed' in everyone

    shown = t['owner'].get(f'/coordinator/registrations/{event_id}?members=unconfirmed').get_data(as_text=True)
    assert 'Waiting Team' in shown and 'Done Team' not in shown

    # Every team confirmed: the filter says nothing matches
    t['db'].collection('registrations').document(waiting_reg).update({'status': 'cancelled'})
    shown = t['owner'].get(f'/coordinator/registrations/{event_id}?members=unconfirmed').get_data(as_text=True)
    assert 'No registrations match this filter.' in shown
