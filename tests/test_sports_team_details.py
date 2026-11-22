"""
tests/test_sports_team_details.py — UPG-405: a sports team registers with its
logo and each player's jersey number; the logo goes into the fixtures and
shows wherever the team does, and the numbers show beside the players' names.
Teams registered before add their numbers on the registration's edit page.
"""
import io

import pytest
from PIL import Image

import routes_forms
import services_live_match as live
from tests.test_live_match import _tap
from tests.test_team_member_confirm import _flashes, team  # noqa: F401

SPORTS = {'category': 'Sports', 'event_type': 'sports_tournament', 'details': {'sport': 'Kabaddi'}}


def _png(width=400, height=400):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    img.paste((200, 30, 30, 255), (width // 4, height // 4, width * 3 // 4, height * 3 // 4))
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


def sports_form(mates: int, lead='7', numbers=None, logo=None) -> dict:
    """A sports team's logo and jersey numbers, as the form sends them: the
    lead's `lead`, member i's `numbers[i]` (else 10 + i)."""
    form = {'lead_jersey': lead, 'team_logo': (io.BytesIO(_png() if logo is None else logo), 'logo.png')}
    for i in range(1, mates + 1):
        form[f'member_{i}_jersey'] = (numbers or {}).get(i, str(10 + i))
    return form


@pytest.fixture
def stored(monkeypatch):
    import utils_storage
    saved = []

    def fake_upload(data, path, content_type):
        saved.append({'data': data, 'path': path, 'type': content_type})
        return f'https://cdn.example/{path}'
    monkeypatch.setattr(utils_storage, 'upload_file', fake_upload)
    return saved


def _send(t, event_id, mates, team_name='Garuda Sena', **extra):
    """The form as a browser sends it: (client, response)."""
    client = t['app'].test_client()
    form = {'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': f"lead{len(t['sent'])}-{team_name[:3]}@test.edu",
            'phone': '9876543210', 'usn': '1SN22CS200', 'team_name': team_name}
    for i, email in enumerate(mates, start=1):
        form.update({f'member_{i}_name': f'Mate {i}', f'member_{i}_email': email})
    form.update(extra)
    return client, client.post(f'/forms/submit/{event_id}', data=form, content_type='multipart/form-data')


def _regs(t, event_id):
    return [d.to_dict() for d in t['db'].collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criteria 1 and 2: the form asks, and keeps them ─────────────────────────

def test_a_sports_team_gives_its_logo_and_every_players_jersey_number(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    page = t['app'].test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in page
    assert 'type="file"' in page and 'name="team_logo"' in page and 'accept="image/png,image/jpeg,image/webp"' in page
    assert 'name="lead_jersey"' in page and 'Your jersey number' in page
    assert 'name="member_1_jersey"' in page and 'name="member_3_jersey"' in page      # a team of up to 4
    assert 'at least 200 × 200 pixels' in page

    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates, team_name='Garuda Sena',
                                 extra=sports_form(2, lead='07', numbers={1: '10', 2: '99'}))
    reg = t['reg'](reg_id)
    assert reg['team_logo'] == f"https://cdn.example/{stored[-1]['path']}"
    assert stored[-1]['path'].startswith(f'team-logos/{event_id}-') and stored[-1]['type'] == 'image/webp'
    with Image.open(io.BytesIO(stored[-1]['data'])) as img:
        assert img.format == 'WEBP' and img.size == (256, 256)
    jerseys = {m['email']: m.get('jersey') for m in reg['members']}
    assert jerseys == {lead: '7', mates[0]: '10', mates[1]: '99'}                    # '07' is 7
    assert reg['form_answers']['lead_jersey'] == '7' and reg['form_answers']['team_logo'] == reg['team_logo']


def test_a_sports_team_is_refused_without_its_logo_or_a_jersey_number(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](2)
    form = sports_form(2)
    del form['team_logo']
    client, resp = _send(t, event_id, mates, **form)
    assert resp.status_code == 302 and "'Team logo' is required." in _flashes(client)

    cases = [
        (sports_form(2, numbers={2: ''}), "Give Mate 2's jersey number."),      # the optional member listed
        (sports_form(2, lead=''), "'Your jersey number' is required."),
        (sports_form(2, numbers={1: '7'}), "You and Mate 1 both have jersey number 7"),
        (sports_form(2, numbers={1: '5', 2: '05'}), "Mate 1 and Mate 2 both have jersey number 5"),
        (sports_form(2, numbers={1: '1000'}), "A jersey number is a whole number from 0 to 999."),
        (sports_form(2, numbers={1: '7.5'}), "A jersey number is a whole number from 0 to 999."),
        (sports_form(2, logo=_png(120, 120)), "too small to show clearly (120 × 120 pixels)"),
        (sports_form(2, logo=b'not an image'), "isn't an image we can read"),
    ]
    for form, message in cases:
        client, resp = _send(t, event_id, mates, **form)
        assert resp.status_code == 302 and message in _flashes(client), (message, _flashes(client))
    assert _regs(t, event_id) == [] and stored == []                             # nothing registered or kept

    # A jersey number twice: the form comes back with what was typed
    client, _ = _send(t, event_id, mates, team_name='Vajra Raiders', **sports_form(2, numbers={1: '7'}))
    page = client.get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'value="Vajra Raiders"' in page and 'value="Mate 2"' in page
    assert "Choose the file again" in page


def test_esports_asks_only_the_logo_and_other_team_events_neither(team, stored):  # noqa: F811
    t = team
    esports = t['event'](category='Sports', event_type='esports')
    page = t['app'].test_client().get(f'/forms/register/{esports}').get_data(as_text=True)
    assert 'name="team_logo"' in page and 'name="lead_jersey"' not in page and '_jersey"' not in page
    mates = t['mates'](1)
    _, reg_id = t['register'](esports, mates, extra={'team_logo': (io.BytesIO(_png()), 'l.png')})
    assert t['reg'](reg_id)['team_logo'].startswith('https://cdn.example/team-logos/')

    other = t['event'](category='Technical')
    page = t['app'].test_client().get(f'/forms/register/{other}').get_data(as_text=True)
    assert 'name="team_logo"' not in page and '_jersey"' not in page and 'multipart/form-data' in page
    _, reg_id = t['register'](other, t['mates'](1))
    assert 'team_logo' not in t['reg'](reg_id) and not any('jersey' in m for m in t['reg'](reg_id)['members'])


def test_the_spoc_adding_a_team_by_hand_may_leave_the_logo_for_later(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    page = t['owner'].get(f'/forms/register/{event_id}?add=team').get_data(as_text=True)
    assert 'name="team_logo"' in page and 'name="team_logo" accept="image/png,image/jpeg,image/webp"\n           required' not in page
    form = sports_form(1)
    del form['team_logo']
    resp = t['owner'].post(f'/forms/submit/{event_id}', content_type='multipart/form-data', data=dict(
        form, add='team', privacy_consent='yes', full_name='Hand Added', email='handadded@test.edu',
        phone='9876543210', team_name='Hand XI', member_1_name='Mate One', member_1_email='mateone@test.edu'))
    assert resp.status_code == 302 and 'is registered' in _flashes(t['owner'])
    [reg] = _regs(t, event_id)
    assert 'team_logo' not in reg and [m.get('jersey') for m in reg['members']] == ['7', '11']


# ── Criteria 3 and 4: the logo and the numbers wherever the team is ─────────

def test_the_logo_and_jersey_numbers_show_wherever_the_team_does(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    _, garuda = t['register'](event_id, t['mates'](1), team_name='Garuda Sena', extra=sports_form(1, lead='7'))
    _, vajra = t['register'](event_id, t['mates'](1), team_name='Vajra', extra=sports_form(1, lead='4'))
    logo = {'Garuda Sena': t['reg'](garuda)['team_logo'], 'Vajra': t['reg'](vajra)['team_logo']}
    assert logo['Garuda Sena'] != logo['Vajra']
    assert t['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'}).status_code == 302
    tournament = t['db'].collection('events').document(event_id).get().to_dict()['tournament']
    assert {x['name']: x.get('logo') for x in tournament['teams']} == logo              # into the fixtures
    ids = {x['name']: x['id'] for x in tournament['teams']}
    [m] = tournament['matches']
    side = 'home' if m['home'] == ids['Garuda Sena'] else 'away'

    live._cache.clear()
    scorer = t['owner'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert scorer.count('data-team-logo') == 2 and logo['Garuda Sena'] in scorer
    assert '<option value="Lena Lead">#7 Lena Lead</option>' in scorer and '#11 Mate 1' in scorer
    assert _tap(t['owner'], event_id, m['id'], op='phase', action='start')[0] == 200
    status, _ = _tap(t['owner'], event_id, m['id'], op='point', team=side, kind='raid', points=3, player='Lena Lead')
    assert status == 200

    live._cache.clear()
    anon = t['app'].test_client()
    pages = {
        'fixtures': anon.get(f'/tournament/fixtures/{event_id}').get_data(as_text=True),
        'scoreboard': anon.get(f"/tournament/live/{event_id}/{m['id']}").get_data(as_text=True),
        'screen': anon.get(f'/tournament/screen/{event_id}/body').get_data(as_text=True),
        'tournament': t['owner'].get(f'/tournament/{event_id}').get_data(as_text=True),
    }
    for name, page in pages.items():
        assert logo['Garuda Sena'] in page and logo['Vajra'] in page, name
    for name in ('fixtures', 'scoreboard', 'screen'):
        assert '<span class="jersey-no" data-jersey>#7</span> ' in pages[name], name
    assert '#4' not in pages['screen']                                              # only who scored


# ── Criterion 5: added later on the edit page ───────────────────────────────

def test_a_team_registered_before_adds_its_jersey_numbers_on_the_edit_page(team, stored):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates, extra=sports_form(2))
    t['db'].collection('registrations').document(reg_id).update({    # as registered before UPG-405
        'members': [{k: v for k, v in m.items() if k != 'jersey'} for m in t['reg'](reg_id)['members']]})
    url = f'/coordinator/registrations/{event_id}/edit/{reg_id}'
    page = t['owner'].get(url).get_data(as_text=True)
    assert 'name="lead_jersey"' in page and 'name="m1_jersey"' in page and 'name="m2_jersey"' in page
    assert 'name="q_team_logo"' not in page and 'name="q_lead_jersey"' not in page     # not questions here

    def form(**changes):
        data = {'lead_name': 'Lena Lead', 'lead_usn': '1SN22CS200', 'lead_phone': '9876543210',
                'team_name': 'Byte Force', 'lead_jersey': '', 'm1_key': mates[0], 'm1_name': 'Mate 1',
                'm1_usn': '1SN22CS201', 'm1_jersey': '', 'm2_key': mates[1], 'm2_name': 'Mate 2',
                'm2_usn': '1SN22CS202', 'm2_jersey': ''}
        data.update(changes)
        return data

    page = t['owner'].post(url, data=form(lead_jersey='9', m1_jersey='9')).get_data(as_text=True)
    assert 'The lead already has jersey number 9' in page
    assert not any(m.get('jersey') for m in t['reg'](reg_id)['members'])
    page = t['owner'].post(url, data=form(m1_jersey='1000')).get_data(as_text=True)
    assert 'A jersey number is a whole number from 0 to 999.' in page

    resp = t['owner'].post(url, data=form(lead_jersey='09', m1_jersey='3', m2_jersey='12'))
    assert resp.status_code == 302
    assert {m['email']: m.get('jersey') for m in t['reg'](reg_id)['members']} == \
        {lead: '9', mates[0]: '3', mates[1]: '12'}
    live._cache.clear()
    assert live.jerseys(t['db'], event_id, [reg_id]) == {reg_id: {'Lena Lead': '9', 'Mate 1': '3', 'Mate 2': '12'}}

    # Another team event's edit page asks no jersey numbers
    other = t['event'](category='Technical')
    _, other_reg = t['register'](other, t['mates'](1))
    page = t['owner'].get(f'/coordinator/registrations/{other}/edit/{other_reg}').get_data(as_text=True)
    assert '_jersey"' not in page


def test_a_jersey_number_may_have_three_digits(team, stored):  # noqa: F811
    """UPG-431: 997 is a jersey number, on the form and on the edit page."""
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates, extra=sports_form(2, lead='100', numbers={1: '997', 2: '007'}))
    assert {m['email']: m.get('jersey') for m in t['reg'](reg_id)['members']} == \
        {lead: '100', mates[0]: '997', mates[1]: '7'}
    field = next(f for f in routes_forms.registration_schema(event_id, t['db'].collection('events').document(
        event_id).get().to_dict())['fields'] if f['id'] == 'member_1_jersey')
    assert field['max'] == 999 and field['pattern'] == r'^\d{1,3}$'

    url = f'/coordinator/registrations/{event_id}/edit/{reg_id}'
    resp = t['owner'].post(url, data={
        'lead_name': 'Lena Lead', 'lead_usn': '1SN22CS200', 'lead_phone': '9876543210', 'team_name': 'Garuda Sena',
        'lead_jersey': '999', 'm1_key': mates[0], 'm1_name': 'Mate 1', 'm1_usn': '1SN22CS201', 'm1_jersey': '998',
        'm2_key': mates[1], 'm2_name': 'Mate 2', 'm2_usn': '1SN22CS202', 'm2_jersey': '0'})
    assert resp.status_code == 302, resp.get_data(as_text=True)[:500]
    assert {m['email']: m.get('jersey') for m in t['reg'](reg_id)['members']} == \
        {lead: '999', mates[0]: '998', mates[1]: '0'}


def test_jersey_rules_in_one_place():
    assert routes_forms.jersey_number(' 07 ') == '7' and routes_forms.jersey_number('') == ''
    event = dict(SPORTS, limits={'team_min': 2, 'team_max': 4})
    assert routes_forms.sports_team_details(event) == {'logo': True, 'jersey': True}
    assert routes_forms.sports_team_details(dict(event, limits={'team_max': 1})) == {'logo': False, 'jersey': False}
    assert routes_forms.jersey_problem(event, '1', [{'name': 'A', 'jersey': '01'}]) == \
        "You and A both have jersey number 1: each player needs their own."
    assert routes_forms.jersey_problem({'category': 'Technical', 'limits': {'team_max': 4}}, '', [{}]) == ''
