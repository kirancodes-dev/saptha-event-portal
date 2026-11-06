"""
tests/test_share_sources.py — UPG-162: where registrations come from. A
visitor's share-link code (`?src=` or `utm_source`) rides with them to the
registration, also after the form's Back and through payment; the sources
table counts registrations and visits per link; an unknown code is "other"
and nothing a visitor types reaches the page as HTML.
"""
import re

import pytest

import services_share
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_paid_events import _verify
from tests.test_ticket_types import shop  # noqa: F401  (fixture)


@pytest.fixture
def promo(real_app):
    flask_app, db = real_app
    owner = f"{_unique('srcspoc')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    spoc = _login(flask_app, owner, 'ClubSPOC')
    event_id = _create_event(spoc, db, _unique('Source Fest'), '2030-09-01', fee=0, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    for label, code in (('Poster', 'poster'), ('Instagram', 'insta')):
        assert spoc.post(f'/spoc/event/{event_id}/share', data={'label': label, 'code': code}).status_code == 302
    return {'app': flask_app, 'db': db, 'spoc': spoc, 'event_id': event_id}


def _form(email, **extra):
    return dict({'privacy_consent': 'yes', 'full_name': 'Sam Source', 'email': email,
                 'phone': '9876543210', 'usn': '1SN22CS077'}, **extra)


def _register(p, client, **extra):
    email = f"{_unique('src')}@test.edu"
    resp = client.post(f"/forms/submit/{p['event_id']}", data=_form(email, **extra))
    assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
    return _reg_of(p, email)


def _reg_of(p, email):
    return next((d.to_dict() for d in p['db'].collection('registrations').where('event_id', '==', p['event_id']).stream()
                 if d.to_dict().get('lead_email') == email), None)


def _hidden_src(page):
    found = re.search(r'name="src" value="([^"]*)"', page)
    return found.group(1) if found else None


def _row(page, code):
    """(visits, registrations, conversion) of one source's table row."""
    row = re.search(r'<tr data-source="%s">(.*?)</tr>' % re.escape(code), page, re.S).group(1)
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
    return cells[1], cells[2], cells[3]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_registration_from_the_poster_keeps_its_source_also_after_back(promo):
    p = promo
    eid = p['event_id']

    # Arrives from the poster, opens the form, goes Back to the event page and
    # opens the form again: the code is still on the form
    visitor = p['app'].test_client()
    assert visitor.get(f'/event/{eid}?src=poster').status_code == 200
    assert _hidden_src(visitor.get(f'/forms/register/{eid}').get_data(as_text=True)) == 'poster'
    assert visitor.get(f'/event/{eid}').status_code == 200                 # Back
    assert _hidden_src(visitor.get(f'/forms/register/{eid}').get_data(as_text=True)) == 'poster'
    assert _register(p, visitor, src='poster')['source'] == 'poster'

    # Sent back with an error, the form keeps it; the session alone is enough too
    other = p['app'].test_client()
    other.get(f'/forms/register/{eid}?src=poster')
    bad = other.post(f'/forms/submit/{eid}', data=_form('not-an-email', src='poster'))
    assert bad.status_code in (302, 303)
    assert _hidden_src(other.get(f'/forms/register/{eid}').get_data(as_text=True)) == 'poster'
    assert _register(p, other)['source'] == 'poster'

    # A browser that lost its session still sends the form's hidden field
    assert _register(p, p['app'].test_client(), src='poster')['source'] == 'poster'

    # The standard utm_source is read too; a direct visit has no source
    utm = p['app'].test_client()
    utm.get(f'/event/{eid}?utm_source=INSTA&utm_medium=social')
    assert _register(p, utm)['source'] == 'insta'
    direct = p['app'].test_client()
    direct.get(f'/event/{eid}')
    assert 'source' not in _register(p, direct)
    assert _hidden_src(direct.get(f'/forms/register/{eid}').get_data(as_text=True)) is None


def test_a_paid_registration_keeps_its_source_through_payment(shop):  # noqa: F811
    d = shop
    owner = f"{_unique('paysrc')}@test.edu"
    _user(d['db'], owner, 'ClubSPOC')
    spoc = _login(d['app'], owner, 'ClubSPOC')
    eid = _create_event(spoc, d['db'], _unique('Paid Source'), '2030-09-02', fee=200, team=False)
    d['db'].collection('events').document(eid).update({'status': 'registration_open'})
    spoc.post(f'/spoc/event/{eid}/share', data={'label': 'Poster', 'code': 'poster'})

    payer = d['app'].test_client()
    payer.get(f'/event/{eid}?src=poster')
    email = f"{_unique('payer')}@test.edu"
    assert payer.post(f'/forms/submit/{eid}', data=_form(email)).status_code == 302
    order = payer.post('/payment/create_order', json={'event_id': eid}).get_json()['order_id']
    assert 'redirect' in _verify(payer, {'event_id': eid}, order, f"pay_{_unique('p')}").get_json()
    reg = next(doc.to_dict() for doc in d['db'].collection('registrations').where('event_id', '==', eid).stream())
    assert reg['lead_email'] == email and reg['payment_status'] == 'Paid' and reg['source'] == 'poster'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_sources_table_counts_registrations_and_visits_per_source(promo):
    p = promo
    eid = p['event_id']
    poster_regs = []
    for i in range(4):                       # four browsers open the poster link…
        client = p['app'].test_client()
        client.get(f'/event/{eid}?src=poster')
        client.get(f'/event/{eid}?src=poster')   # …a reload isn't a second visit
        if i < 3:
            poster_regs.append(_register(p, client))
    insta = p['app'].test_client()
    insta.get(f'/event/{eid}?src=insta')
    _register(p, insta)
    _register(p, p['app'].test_client())     # direct
    # A cancelled registration isn't counted
    cancelled = next(d.id for d in p['db'].collection('registrations').where('event_id', '==', eid).stream()
                     if d.to_dict().get('lead_email') == poster_regs[0]['lead_email'])
    p['db'].collection('registrations').document(cancelled).update({'status': 'Cancelled'})

    rows = {r['code']: r for r in services_share.report(p['db'], eid,
                                                         p['db'].collection('events').document(eid).get().to_dict())}
    assert (rows['poster']['visits'], rows['poster']['registrations'], rows['poster']['conversion']) == (4, 2, 50.0)
    assert (rows['insta']['visits'], rows['insta']['registrations'], rows['insta']['conversion']) == (1, 1, 100.0)
    assert rows['']['registrations'] == 1 and rows['']['visits'] is None
    assert rows['other']['registrations'] == 0

    page = p['spoc'].get(f'/spoc/event/{eid}/share').get_data(as_text=True)
    assert _row(page, 'poster') == ('4', '2', '50.0%')
    assert _row(page, 'insta') == ('1', '1', '100.0%')
    assert _row(page, 'direct') == ('—', '1', '—')
    assert f'/event/{eid}?src=poster' in page and f'/spoc/event/{eid}/share/poster/qr.png' in page
    qr = p['spoc'].get(f'/spoc/event/{eid}/share/poster/qr.png')
    assert qr.status_code == 200 and qr.mimetype == 'image/png'
    assert p['spoc'].get(f'/spoc/event/{eid}/share/nope/qr.png').status_code == 404

    # A removed link's registrations stay counted under its code
    p['spoc'].post(f'/spoc/event/{eid}/share', data={'action': 'remove', 'code': 'insta'})
    page = p['spoc'].get(f'/spoc/event/{eid}/share').get_data(as_text=True)
    assert 'insta (link removed)' in page and _row(page, 'insta')[1] == '1'


def test_only_the_events_organisers_see_and_change_the_links(promo):
    p = promo
    eid = p['event_id']
    stranger = f"{_unique('srcother')}@test.edu"
    _user(p['db'], stranger, 'ClubSPOC')
    outsider = _login(p['app'], stranger, 'ClubSPOC')
    assert outsider.get(f'/spoc/event/{eid}/share').status_code == 403
    assert outsider.post(f'/spoc/event/{eid}/share', data={'label': 'Mine'}).status_code == 403
    assert outsider.get(f'/spoc/event/{eid}/share/poster/qr.png').status_code == 403
    assert [link['code'] for link in services_share.links_for(
        p['db'].collection('events').document(eid).get().to_dict())] == ['poster', 'insta']


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_an_unknown_code_is_other_and_cant_inject_html(promo):
    p = promo
    eid = p['event_id']
    nasty = '<script>alert(1)</script>'
    visitor = p['app'].test_client()
    visitor.get(f'/event/{eid}', query_string={'src': nasty})
    assert _hidden_src(visitor.get(f'/forms/register/{eid}').get_data(as_text=True)) == 'other'
    assert _register(p, visitor)['source'] == 'other'
    # A forged hidden field is checked again on submit
    assert _register(p, p['app'].test_client(), src='"><img src=x onerror=alert(2)>')['source'] == 'other'
    assert _register(p, p['app'].test_client(), src='nosuchlink')['source'] == 'other'

    # The organiser's own label shows as text; a code that isn't a slug is refused
    p['spoc'].post(f'/spoc/event/{eid}/share', data={'label': '<b>Bold</b> <img src=y onerror=alert(3)>'})
    p['spoc'].post(f'/spoc/event/{eid}/share', data={'label': 'Bad', 'code': '"><script>'})
    p['spoc'].post(f'/spoc/event/{eid}/share', data={'label': 'Kept', 'code': 'other'})
    codes = [link['code'] for link in services_share.links_for(
        p['db'].collection('events').document(eid).get().to_dict())]
    assert codes == ['poster', 'insta', 'b-bold-b-img-src-y-onerror-alert']   # cut at 32

    page = p['spoc'].get(f'/spoc/event/{eid}/share').get_data(as_text=True)
    assert _row(page, 'other')[1] == '3'
    assert '<script>alert(1)' not in page and '<img src=x' not in page and '<img src=y' not in page
    assert '&lt;b&gt;Bold&lt;/b&gt;' in page
    with pytest.raises(services_share.ShareError):
        services_share.add_link(p['db'], eid, {}, 'X', 'Has Space')
