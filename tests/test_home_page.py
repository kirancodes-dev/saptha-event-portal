"""
tests/test_home_page.py — UPG-86: the public home page shows the university's
real details (from university_info.py) and live events from the database, and
nothing invented: no fixed entry fee, no zero "Registrations", no "under 60
seconds" steps, no made-up testimonials or count-ups, and no dead links.
"""
import datetime
import os
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from university_info import UNIVERSITY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def home(real_app, monkeypatch):
    flask_app, db = real_app
    spoc = f"{_unique('homespoc')}@test.edu"
    before = {d.id for d in db.collection('users').stream()}
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    today = datetime.date.today()
    made = {}
    for key, offset, extra in (('next', 3, {}), ('later', 40, {}), ('past', -5, {}),
                               ('closed', 6, {'deadline': (today - datetime.timedelta(days=1)).isoformat()})):
        title = _unique(f'Home {key}')
        eid = _create_event(client, db, title, (today + datetime.timedelta(days=offset)).isoformat(), team=False)
        db.collection('events').document(eid).update(dict({'status': 'registration_open'}, **extra))
        made[key] = (eid, title)
    page = flask_app.test_client().get('/').get_data(as_text=True)
    yield page, made
    for d in db.collection('users').stream():
        if d.id not in before:
            db.collection('users').document(d.id).delete()


def _hero(page):
    return page[page.index('id="hero"'):page.index('id="events"')]


def test_nothing_invented_is_left_on_the_home_page(home):
    page, _ = home
    hero = _hero(page)
    assert '₹0' not in hero and 'Entry Fee' not in hero and '>Registrations<' not in hero
    assert 'Grand College Fest' not in page
    for gone in ('Under 60 Seconds', 'How It Works', 'What Students Say', 'data-count=', 'stat-counter',
                 'Anirudh J.', 'Priya K.', 'Rohan V.'):
        assert gone not in page, gone
    assert 'registered</div>' not in page          # the cached counter isn't shown on cards
    assert 'href="/calendar"' not in page            # the calendar isn't on the home page (owner, UPG-87)


def test_coming_up_lists_the_next_open_events_from_the_database(home):
    page, made = home
    hero = _hero(page)
    # Other tests share the database, so check the rule rather than one event:
    # the earliest open events, soonest first, never past or closed ones
    dates = re.findall(r'<span class="visually-hidden">, (\d{4}-\d{2}-\d{2})</span>', hero)
    today = datetime.date.today().isoformat()
    next_date = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    assert 1 <= len(dates) <= 3 and dates == sorted(dates) and all(d >= today for d in dates)
    assert made['next'][1] in hero or all(d <= next_date for d in dates)
    assert made['past'][1] not in hero and made['closed'][1] not in hero
    assert re.search(r'\d+ open for registration', hero)


def test_real_university_details_and_links(home):
    page, _ = home
    for sm in UNIVERSITY['social']:
        assert f'href="{sm["url"]}"' in page, sm['name']
    for link in UNIVERSITY['links']:
        assert f'href="{link["url"]}"' in page, link['label']
    for school in UNIVERSITY['schools']:
        assert school['name'].replace('&', '&amp;') in page
    assert UNIVERSITY['tagline'] in page and UNIVERSITY['email'] in page
    # No social button points nowhere, and none of the old links that only reach
    # the university site's catch-all page are left
    assert not re.search(r'class="soc-btn"[^>]*href="#"|href="#"[^>]*class="soc-btn"', page)
    for dead in ('about-us/', 'departments/', 'news-events/', 'human-resource-development-hrd/'):
        assert f'href="https://snpsu.edu.in/{dead}"' not in page
    assert '"sameAs"' in page


def test_one_footer_and_working_category_chips(home):
    page, _ = home
    assert page.count('<footer') == 1
    with open(os.path.join(ROOT, 'static/js/pages/index.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert 'function filterByCategory(' in js          # the hero chips call it
    assert 'showToast' not in js                       # script errors never pop up for visitors
