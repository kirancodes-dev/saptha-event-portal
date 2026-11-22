"""
tests/test_player_details.py — UPG-423: a sports team's players give their
date of birth and position (Raider, Defender, All-rounder: kabaddi's), both
optional. The form saves them on each player, the organiser corrects them on
the registration's Edit page, and a player confirming their place checks
their own. A player profile (UPG-424) shows the age, never the date.
"""
import datetime

import routes_forms
from tests import test_team_member_confirm as _tc
from tests.test_sports_team_details import SPORTS, _send, sports_form, stored  # noqa: F401
from tests.test_team_member_confirm import NEW_PASSWORD, _flashes, _link, _to

team = _tc.team   # UPG-207's fixture


def _years_ago(years, days=0):
    today = datetime.date.today()
    return (today.replace(year=today.year - years) - datetime.timedelta(days=days)).isoformat()


# ── Criterion 1: the form asks, optional, and saves them on each player ─────

def test_a_sports_team_form_asks_each_players_date_of_birth_and_position(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    page = t['app'].test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    for name in ('lead_dob', 'lead_position', 'member_1_dob', 'member_1_position', 'member_3_dob'):
        assert f'name="{name}"' in page, name
    assert 'type="date"' in page and 'Your date of birth' in page and 'Your position' in page
    for p in ('Raider', 'Defender', 'All-rounder'):
        assert f'<option value="{p}"' in page
    assert page.count('name="lead_dob"') == 1
    fields = {f['id']: f for f in routes_forms.registration_schema(
        event_id, t['db'].collection('events').document(event_id).get().to_dict())['fields']}
    assert not any(fields[k]['required'] for k in ('lead_dob', 'lead_position', 'member_1_dob', 'member_1_position'))

    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates, extra=dict(
        sports_form(2), lead_dob='2004-03-09', lead_position='Raider',
        member_1_dob='2005-11-30', member_1_position='All-rounder'))            # Mate 2 gives neither
    members = {m['email']: m for m in t['reg'](reg_id)['members']}
    assert (members[lead]['dob'], members[lead]['position']) == ('2004-03-09', 'Raider')
    assert (members[mates[0]]['dob'], members[mates[0]]['position']) == ('2005-11-30', 'All-rounder')
    assert 'dob' not in members[mates[1]] and 'position' not in members[mates[1]]


def test_only_kabaddi_asks_the_position_and_esports_asks_neither(team, stored):  # noqa: F811
    t = team
    cricket = t['event'](category='Sports', event_type='sports_tournament', details={'sport': 'Cricket'})
    page = t['app'].test_client().get(f'/forms/register/{cricket}').get_data(as_text=True)
    assert 'name="member_1_dob"' in page and '_position"' not in page
    esports = t['event'](category='Sports', event_type='esports')
    page = t['app'].test_client().get(f'/forms/register/{esports}').get_data(as_text=True)
    assert '_dob"' not in page and '_position"' not in page
    other = t['event'](category='Technical')
    page = t['app'].test_client().get(f'/forms/register/{other}').get_data(as_text=True)
    assert '_dob"' not in page and '_position"' not in page


# ── Criterion 2: a future date, a player under 10, a position not offered ───

def test_a_date_in_the_future_a_player_under_ten_or_another_position_is_refused(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](2)
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    cases = [
        ({'lead_dob': tomorrow}, "A date of birth can't be in the future."),
        ({'member_1_dob': _years_ago(10, days=-1)}, "A player is at least 10 years old"),   # 10 tomorrow
        ({'member_2_dob': '30/11/2005'}, "A date of birth is a date like 2005-08-14."),
        ({'member_1_position': 'Goalkeeper'}, "Choose from the options given for 'Member 2 Position'."),
    ]
    for extra, message in cases:
        client, resp = _send(t, event_id, mates, **dict(sports_form(2), **extra))
        assert resp.status_code == 302 and message in _flashes(client), (message, _flashes(client))
    assert not list(t['db'].collection('registrations').where('event_id', '==', event_id).stream())
    assert routes_forms.birth_date_problem(_years_ago(10)) == ''                          # 10 today is fine
    assert routes_forms.age_on('2004-03-09', datetime.date(2026, 3, 8)) == 21
    assert routes_forms.age_on('2004-03-09', datetime.date(2026, 3, 9)) == 22


# ── Criterion 3: the Edit page shows and corrects them ──────────────────────

def test_the_edit_page_shows_and_corrects_the_date_of_birth_and_position(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](1)
    lead, reg_id = t['register'](event_id, mates, extra=dict(sports_form(1), member_1_dob='2005-11-30',
                                                               member_1_position='Defender'))
    url = f'/coordinator/registrations/{event_id}/edit/{reg_id}'
    page = t['owner'].get(url).get_data(as_text=True)
    assert 'name="lead_dob"' in page and 'name="lead_position"' in page
    assert 'name="m1_dob"' in page and 'value="2005-11-30"' in page
    assert '<option value="Defender" selected>' in page
    assert 'name="q_lead_dob"' not in page and 'name="q_lead_position"' not in page     # not questions here

    def form(**changes):
        data = {'lead_name': 'Lena Lead', 'lead_usn': '1SN22CS200', 'lead_phone': '9876543210',
                'team_name': 'Byte Force', 'lead_jersey': '7', 'lead_dob': '', 'lead_position': '',
                'm1_key': mates[0], 'm1_name': 'Mate 1', 'm1_usn': '1SN22CS201', 'm1_jersey': '11',
                'm1_dob': '2005-11-30', 'm1_position': 'Defender'}
        data.update(changes)
        return data

    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    page = t['owner'].post(url, data=form(m1_dob=tomorrow)).get_data(as_text=True)
    assert "A date of birth can&#39;t be in the future." in page
    page = t['owner'].post(url, data=form(lead_position='Striker')).get_data(as_text=True)
    assert 'Choose from the options given' in page
    assert t['member'](reg_id, mates[0])['dob'] == '2005-11-30'                       # nothing saved

    resp = t['owner'].post(url, data=form(lead_dob='2003-01-15', lead_position='All-rounder',
                                          m1_dob='2005-12-01', m1_position='Raider'))
    assert resp.status_code == 302
    lead_row, mate = t['member'](reg_id, lead), t['member'](reg_id, mates[0])
    assert (lead_row['dob'], lead_row['position']) == ('2003-01-15', 'All-rounder')
    assert (mate['dob'], mate['position']) == ('2005-12-01', 'Raider')


# ── Criterion 4: a player confirming their place checks their own ───────────

def test_a_player_confirming_their_place_checks_their_date_of_birth_and_position(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](member_confirm=True, **SPORTS)                       # the organiser turned it on
    mates = t['mates'](1)
    t['sent'].clear()
    lead, reg_id = t['register'](event_id, mates, extra=dict(sports_form(1), member_1_dob='2005-11-30'))
    link = _link(_to(t['sent'], mates[0])[0])
    visitor = t['app'].test_client()
    page = visitor.get(link).get_data(as_text=True)
    assert 'data-member-dob' in page and 'value="2005-11-30"' in page and 'data-member-position' in page
    assert 'never the date' in page

    details = {'details': '1', 'name': 'Mate 1', 'usn': '', 'phone': '',
               'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD}
    visitor.post(link, data=dict(details, dob='2020-01-01', position='Raider'))        # 6 years old
    assert 'A player is at least 10 years old' in _flashes(visitor)
    assert not t['member'](reg_id, mates[0]).get('confirmed_at')
    visitor = t['app'].test_client()
    visitor.post(link, data=dict(details, dob='2005-10-30', position='Libero'))
    assert 'Choose your position from the list' in _flashes(visitor)

    visitor = t['app'].test_client()
    resp = visitor.post(link, data=dict(details, dob='2005-10-30', position='Raider'))
    assert resp.status_code == 302
    mate = t['member'](reg_id, mates[0])
    assert mate['confirmed_at'] and (mate['dob'], mate['position']) == ('2005-10-30', 'Raider')
