"""
tests/test_badges.py — UPG-158: name badges as A4 sheets of 8 and one at a
time from the scanner, with the registration's QR that every scanner accepts,
no phone or email on paper, and only the event's check-in staff printing.
"""
import io

import pypdfium2
import pytest

import services_badges
from tests.test_checkin_unified import _registration, _scan, gate  # noqa: F401  (fixture)
from tests.test_integration_flow import _login, _unique, _user


@pytest.fixture
def qr_texts(monkeypatch):
    """What each badge's QR encodes, as the PDF is drawn."""
    seen = []
    real = services_badges._qr_image
    monkeypatch.setattr(services_badges, '_qr_image', lambda text: seen.append(text) or real(text))
    return seen


def _pages(pdf_bytes):
    doc = pypdfium2.PdfDocument(io.BytesIO(pdf_bytes))
    return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_sheet_has_one_badge_per_confirmed_registration_8_a_page(gate, qr_texts):  # noqa: F811
    d = gate
    names = []
    for i in range(10):
        reg_id, _ = _registration(d, lead_name=f'Badge Person {i:02d}', status='Confirmed')
        names.append(f'Badge Person {i:02d}')
    _registration(d, lead_name='Gone Cancelled', status='Cancelled')
    _registration(d, lead_name='Still Paying', status='pending_payment')
    resp = d['staff'].get(f"/ticket/badges/{d['event_id']}.pdf")
    assert resp.status_code == 200 and resp.mimetype == 'application/pdf'
    pages = _pages(resp.data)
    # 10 written here plus the fixture's registrant, and the assigned coordinator's role badge
    assert len(pages) == 2
    assert all(n in pages[0] + pages[1] for n in names + ['Tara Ticket'])
    assert 'Gone Cancelled' not in ''.join(pages) and 'Still Paying' not in ''.join(pages)
    assert sum(p.count('Badge Person') for p in pages[:1]) + pages[0].count('Tara Ticket') == 8
    assert 'STAFF' in pages[1]

    # Every QR is a ticket the scanner accepts, once per registration
    assert len(qr_texts) == 11
    first = _scan(d['staff'], qr_texts[0], d['event_id'])
    assert first.status_code == 200 and first.get_json()['status'] == 'success'


def test_a_team_gets_a_badge_per_member_with_its_qr(gate, qr_texts):  # noqa: F811
    d = gate
    reg_id, _ = _registration(d, lead_name='Lead Lata', team_name='Byte Force', status='Confirmed',
                              members=[{'name': 'Lead Lata', 'email': 'x@test.edu', 'role': 'Lead'},
                                       {'name': 'Mate Mohan', 'email': 'm@test.edu'}],
                              lead_email='x@test.edu')
    resp = d['staff'].get(f'/ticket/{reg_id}/badge.pdf')
    assert resp.status_code == 200
    pages = _pages(resp.data)
    assert len(pages) == 2 and 'Lead Lata' in pages[0] and 'Mate Mohan' in pages[1]
    assert 'Team Byte Force' in pages[0] and len(set(qr_texts)) == 1


def test_the_scanner_gives_the_badge_link_after_a_check_in(gate):  # noqa: F811
    d = gate
    reg_id, token = _registration(d, lead_name='Door Dina', status='Confirmed')
    body = _scan(d['staff'], token, d['event_id']).get_json()
    assert body['status'] == 'success' and body['badge_url'] == f'/ticket/{reg_id}/badge.pdf'
    assert d['staff'].get(body['badge_url']).status_code == 200


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_badge_never_shows_a_phone_or_email(gate):  # noqa: F811
    d = gate
    reg_id, _ = _registration(d, lead_name='Private Priya', status='Confirmed', lead_phone='9123456789',
                              lead_email='priya.private@test.edu', participant_type='external',
                              institution='RV College', phone='9123456789',
                              members=[{'name': 'Mem Ber', 'email': 'member.mail@test.edu', 'phone': '9988776655'}])
    for url in (f"/ticket/badges/{d['event_id']}.pdf", f'/ticket/{reg_id}/badge.pdf'):
        text = ''.join(_pages(d['staff'].get(url).data))
        assert 'Private Priya' in text and 'RV College' in text
        for secret in ('9123456789', '9988776655', 'priya.private', 'member.mail', '@'):
            assert secret not in text


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_only_the_events_staff_can_print(gate):  # noqa: F811
    d = gate
    reg_id = d['reg_id']
    urls = (f"/ticket/badges/{d['event_id']}.pdf", f'/ticket/{reg_id}/badge.pdf')
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    other_spoc = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other_spoc, 'ClubSPOC')
    for client in (d['student'], outsider, _login(d['app'], other_spoc, 'ClubSPOC')):
        for url in urls:
            assert client.get(url).status_code == 403, url
    for client in (d['owner'], d['staff']):
        for url in urls:
            assert client.get(url).status_code == 200, url
    assert d['app'].test_client().get(urls[0]).status_code == 302   # logged out: to the login page
