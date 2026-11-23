"""
tests/test_sheet_pools.py — UPG-459: the owner's fixture sheet alternates the
pools (a Pool B match, then a Pool A one, …). Uploaded, each match takes the
pool its two teams are in, with that pool's rounds in the sheet's order, so the
cards and the audience's pool pick follow the sheet. Team names are made up
(as on the owner's sheet).
"""
from tests.test_fixture_sheet_upload import _upload, _xlsx
from tests.test_kabaddi_premier_league import _form, _generate, league  # noqa: F401
from tests.test_sports_tournament import _t, cup  # noqa: F401

HEAD = ['Match', 'Stage', 'Team 1', 'Team 2']
# The owner's sheet as typed: M-01's and M-02's "Pole" are swapped on the paper
SHEET = [
    ['M-01', 'POLE A - LEAGUE', 'Gaja Pade', 'Code Blue'],
    ['M-02', 'POLE B - LEAGUE', 'Garuda Sena', 'Malnad Fighters'],
    ['M-03', 'POLE A - LEAGUE', 'Neuro Ninjas', 'Vajra'],
    ['M-04', 'POLE B - LEAGUE', 'Veera Yodha', 'Gandaberunda Warriors'],
    ['M-05', 'POLE A - LEAGUE', 'Garuda Sena', 'Neuro Ninjas'],
    ['M-06', 'POLE B - LEAGUE', 'Gaja Pade', 'Veera Yodha'],
    ['M-07', 'POLE A - LEAGUE', 'Malnad Fighters', 'Vajra'],
    ['M-08', 'POLE B - LEAGUE', 'Code Blue', 'Gandaberunda Warriors'],
    ['M-09', 'POLE A - LEAGUE', 'Garuda Sena', 'Vajra'],
    ['M-10', 'POLE B - LEAGUE', 'Gaja Pade', 'Gandaberunda Warriors'],
    ['M-11', 'POLE A - LEAGUE', 'Malnad Fighters', 'Neuro Ninjas'],
    ['M-12', 'POLE B - LEAGUE', 'Code Blue', 'Veera Yodha'],
    ['M-13', 'INTER-POLE (A1 vs B1)', 'Garuda Sena', 'Gaja Pade'],
    ['M-14', 'INTER-POLE (A2 vs B2)', 'Malnad Fighters', 'Code Blue'],
    ['M-15', 'INTER-POLE (A3 vs B3)', 'Neuro Ninjas', 'Veera Yodha'],
    ['M-16', 'INTER-POLE (A4 vs B4)', 'Vajra', 'Gandaberunda Warriors'],
]


def _labels(t):
    out = []
    for m in t['matches']:
        out.append('X' if m.get('cross') else f"{m['pool']}{m['round']}")
    return out


def test_the_owners_sheet_puts_each_match_in_its_teams_pool_in_the_sheets_order(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids, **_form(ids, legs='1'))
    assert len(t['matches']) == 16 and _labels(t)[:2] == ['A1', 'A1']      # as generated: pool A's six first
    page = _upload(d['owner'], event_id, _xlsx([HEAD] + SHEET), 'fixtures.xlsx')
    assert 'Schedule saved' in page
    t = _t(d, event_id)
    names = {x['id']: x['name'] for x in t['teams']}
    assert [[names[m['home']], names[m['away']]] for m in t['matches']] == [r[2:] for r in SHEET]
    # Each match in its teams' pool (M-01 is two pool B teams), each pool's rounds in the sheet's order
    assert _labels(t) == ['B1', 'A1', 'A1', 'B1', 'A2', 'B2', 'A2', 'B2', 'A3', 'B3', 'A3', 'B3', 'X', 'X', 'X', 'X']
    # The cards and the audience's pool pick follow it
    fixtures = d['owner'].get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'M-01 · Pool B · League round 1' in fixtures and 'M-02 · Pool A · League round 1' in fixtures
    pool_a = d['owner'].get(f'/tournament/fixtures/{event_id}?pool=A').get_data(as_text=True)
    assert 'data-match-card="m2"' in pool_a and 'data-match-card="m1"' not in pool_a
    # The tables were right all along: each team in its own pool
    assert {x['name']: x['pool'] for x in t['teams']}['Gaja Pade'] == 'B'


def test_the_same_sheet_again_sets_the_pools_even_with_the_teams_unchanged(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids, **_form(ids, legs='1'))
    t = _t(d, event_id)
    # As on the live site before UPG-459: the teams set by an earlier upload, the pools not
    names = {x['name']: x['id'] for x in t['teams']}
    for m, row in zip(t['matches'], SHEET):
        m['home'], m['away'] = names[row[2]], names[row[3]]
    d['db'].collection('events').document(event_id).update({'tournament': t})
    assert _labels(_t(d, event_id))[0] == 'A1'
    assert 'Schedule saved' in _upload(d['owner'], event_id, _xlsx([HEAD] + SHEET), 'fixtures.xlsx')
    assert _labels(_t(d, event_id))[:4] == ['B1', 'A1', 'A1', 'B1']


def test_a_pair_from_two_pools_outside_the_inter_pool_round_changes_nothing(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids, **_form(ids, legs='1'))
    before = _t(d, event_id)['matches']
    wrong = [list(r) for r in SHEET]
    wrong[0][3] = 'Vajra'                       # Gaja Pade (B) v Vajra (A) as a pool match
    wrong[12][3] = 'Malnad Fighters'            # Garuda Sena v Malnad Fighters (both A) as inter-pool
    page = _upload(d['owner'], event_id, _xlsx([HEAD] + wrong), 'fixtures.xlsx')
    assert 'Nothing was changed.' in page
    assert 'Gaja Pade is in pool B and Vajra in pool A' in page
    assert 'it is an inter-pool match, but Garuda Sena and Malnad Fighters are both in pool A' in page
    assert _t(d, event_id)['matches'] == before
