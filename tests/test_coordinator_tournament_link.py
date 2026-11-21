"""
tests/test_coordinator_tournament_link.py — UPG-387: an assigned coordinator
scores the matches, but their dashboard had no way to the tournament page.
A sports event's card now links "Matches & live scoring"; other events don't.
"""
from tests.test_sports_tournament import cup  # noqa: F401


def test_a_sports_event_card_links_the_matches_for_its_coordinator(cup):  # noqa: F811
    d = cup
    event_id, _ids = d['event'](['Ants', 'Bees'])
    d['db'].collection('events').document(event_id).update({'status': 'active'})
    page = d['coord'].get('/coordinator/dashboard').get_data(as_text=True)
    assert f'href="/tournament/{event_id}"' in page and 'data-tournament-link' in page
    assert 'Matches &amp; live scoring' in page
    assert d['coord'].get(f'/tournament/{event_id}').status_code == 200        # and the link opens

    d['db'].collection('events').document(event_id).update({'category': 'Technical', 'status': 'active'})
    page = d['coord'].get('/coordinator/dashboard').get_data(as_text=True)
    assert f'href="/tournament/{event_id}"' not in page                        # not a sports event
