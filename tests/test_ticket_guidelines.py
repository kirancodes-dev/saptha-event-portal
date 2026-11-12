"""
tests/test_ticket_guidelines.py — UPG-242 on the real database layer.

The back of the ticket showed four fixed "venue guidelines" and a fixed
contact for every event (owner's screenshot of SAPTHAHACKS'26, 2026-11-12).
The SPOC now types the event's own guidelines (one per line; numbering like
"01." taken off) and a support email on the event's edit page. The ticket
shows them; the registration email and the waitlist emails say "Questions?
Write to ...". An event without them keeps the general guidelines.
"""
import utils_email
from tests import test_spoc_cancel_team as _cancel
from tests.test_integration_flow import _login, _user

host = _cancel.host   # UPG-211's fixture: an event's hosting SPOC, register(), emails

RULES = """01.Only Sapthagiri NPS University students can participate.

03.Carry your university ID card during reporting.
10.Report at the designated time.
14.Plagiarism or copying another team's work is prohibited."""


def _edit(h, event_id, **fields):
    data = dict({'contact_sent': '1'}, **fields)
    return h['owner'].post(f'/spoc/edit_event/{event_id}', data=data)


def _ticket(h, event_id, lead, reg_id):
    _user(h['db'], lead, 'Student')
    return _login(h['app'], lead, 'Student').get(f'/ticket/{reg_id}').get_data(as_text=True)


def test_the_spocs_guidelines_and_support_email_show_on_the_ticket(host):
    h = host
    event_id = h['event']()
    assert _edit(h, event_id, ticket_guidelines=RULES, support_email='InnovEdge.SNPSU@gmail.com').status_code == 302
    event = h['db'].collection('events').document(event_id).get().to_dict()
    assert event['support_email'] == 'innovedge.snpsu@gmail.com'
    assert event['ticket_guidelines'].split('\n') == [
        'Only Sapthagiri NPS University students can participate.',
        'Carry your university ID card during reporting.', 'Report at the designated time.',
        "Plagiarism or copying another team's work is prohibited."]
    assert 'innovedge.snpsu@gmail.com' in h['owner'].get(f'/spoc/edit_event/{event_id}').get_data(as_text=True)

    reg_id, lead, _ = h['register'](event_id)
    page = _ticket(h, event_id, lead, reg_id)
    back = page[page.index('data-ticket-guidelines'):]
    back = back[:back.index('</ul>')]
    assert 'Carry your university ID card during reporting.' in back and 'Report at the designated time.' in back
    assert 'brightness' not in back and 'food or beverages' not in back
    assert 'Event Guidelines' in page
    assert 'data-ticket-support' in page and 'mailto:innovedge.snpsu@gmail.com' in page


def test_an_event_without_them_keeps_the_general_guidelines(host):
    h = host
    event_id = h['event']()
    reg_id, lead, _ = h['register'](event_id)
    page = _ticket(h, event_id, lead, reg_id)
    assert 'Set mobile screen brightness to maximum for QR scanning.' in page and 'data-ticket-support' not in page


def test_a_bad_support_email_is_refused(host):
    h = host
    event_id = h['event']()
    _edit(h, event_id, support_email='not an email', ticket_guidelines='Be on time.')
    event = h['db'].collection('events').document(event_id).get().to_dict()
    assert not event.get('support_email') and not event.get('ticket_guidelines')


def test_the_registration_email_says_where_to_write(host, monkeypatch):
    h = host
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, **kw: sent.append(
        {'to': to, 'subject': subject, 'html': html}) or True)
    event_id = h['event']()
    _edit(h, event_id, support_email='innovedge.snpsu@gmail.com')
    _, lead, _ = h['register'](event_id)
    [mail] = [m for m in sent if m['to'] == lead]
    assert 'Questions? Write to' in mail['html'] and 'mailto:innovedge.snpsu@gmail.com' in mail['html']


def test_the_waitlist_seat_email_says_where_to_write(host):
    from tests.test_seat_email import _taker
    from tests.test_spoc_waitlist import _full_event, _join
    h = host
    event_id = _full_event(h)
    _edit(h, event_id, support_email='innovedge.snpsu@gmail.com')
    _, lead, _ = _join(h, event_id, 'Next In')
    h['emails'].clear()
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    [mail] = [m for m in h['emails'] if m['to'] == lead]
    assert 'Questions? Write to innovedge.snpsu@gmail.com' in mail['message']
