"""
tests/test_score_sheet_look.py — UPG-472, the owner, 24 Nov 2026: "this pdf
need to have the logo and proper structure so that will be easy to
understand". The score sheet has the college's logo at the top, each team's
logo (or its initials) over its name and score, the points by half under each
team's own columns, each team's players in its own table, signature lines and
a footer on every page. A team with a logo no longer stops the sheet. Made-up
names.
"""
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

import services_live_match as live
import services_score_sheet
import services_sports
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _raid, _started, _to_full_time
from tests.test_sports_tournament import cup  # noqa: F401


def _get(d, event_id, m):
    live._cache.clear()
    resp = d['app'].test_client().get(f"/tournament/live/{event_id}/{m['id']}/sheet.pdf")
    assert resp.status_code == 200 and resp.mimetype == 'application/pdf', resp.status_code
    return resp.data


pages = []


def _read(data):
    """(the text, the number of pictures on page 1); `pages` holds the page count."""
    doc = pdfium.PdfDocument(data)
    try:
        text = ' '.join('\n'.join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        pictures = len(list(doc[0].get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=5)))
        pages.append(len(doc))
        return text, pictures
    finally:
        doc.close()


def _set_logo(d, event_id, team_id, url):
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    t = services_sports.set_logo(t, team_id, url)
    d['db'].collection('events').document(event_id).update({'tournament': t})


def test_the_sheet_has_the_college_logo_and_a_clear_layout(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    _to_full_time(d, event_id, m)
    text, pictures = _read(_get(d, event_id, m))
    assert pictures == 1                                         # the college's logo (no team logos yet)
    assert pages[-1] == 1                                        # a match's sheet fits on one page
    assert text.count('Pool A') == 1                             # the stage already says the pool
    title = d['db'].collection('events').document(event_id).get().to_dict()['title']
    # The order a reader meets it: the event, the score, the result, the halves, line-ups, players, signatures
    body = text[text.index(title):]                              # the footer comes first in the text
    order = [title, 'Score sheet', 'Garuda Sena', 'Vajra', 'Result:', 'Points by half', '1st half', '2nd half',
             'Line-ups', "Players' points", "Officials' signatures", 'Scorer', 'Referee']
    at, start = [], 0
    for x in order:
        assert x in body[start:], (x, body[start:start + 300])
        start = body.index(x, start)
        at.append(start)
    assert 'Page 1' in text and 'printed' in text and 'IST' in text   # the footer
    # Each team's players are in its own table under its name: no "Team" column
    players = text[text.index("Players' points"):text.index("Officials' signatures")]
    assert players.index('Garuda Sena') < players.index('Arjun') < players.index('Vajra')
    assert 'No. Player Raid Tackle Total' in players


def test_a_team_with_a_logo_gets_its_logo_on_the_sheet(league):  # noqa: F811
    """Before UPG-472, a team with a logo made the sheet fail."""
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _set_logo(d, event_id, m['home'], '/static/img/campus-800.webp')
    _started(d, event_id, m)
    text, pictures = _read(_get(d, event_id, m))
    assert pictures == 2 and 'Garuda Sena' in text               # the college's and the home team's
    _set_logo(d, event_id, m['away'], '/static/img/no-such-logo.webp')
    text, pictures = _read(_get(d, event_id, m))                 # a logo that can't be read: initials, no failure
    assert pictures == 2 and 'Vajra' in text


def test_the_logo_reader_gives_png_bytes_or_none():
    png = services_score_sheet._logo('/static/img/campus-800.webp')
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    assert services_score_sheet._logo('') is None
    assert services_score_sheet._logo('http://example.com/x.png') is None      # only our https storage
    assert services_score_sheet._initials('Garuda Sena') == 'GS' and services_score_sheet._initials('') == '?'
