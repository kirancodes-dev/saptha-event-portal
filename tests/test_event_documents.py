"""
tests/test_event_documents.py — UPG-239 on the real database layer.

The hosting SPOC adds a document for registered teams on the registrations
page: a title, their own instructions and a PDF (an undertaking form, say),
or one of the two. Each registered lead is told in the portal; the lead and
the members see it on their dashboard, read the instructions and download the
PDF. Nobody else downloads it; another SPOC can't add or remove; the SPOC
removes one.
"""
import pytest

from tests import test_spoc_cancel_team as _cancel
from tests.test_integration_flow import _login, _unique, _user

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
INSTRUCTIONS = "Print it, sign it and hand it in at room 204\nbefore 10 am on the event day."


@pytest.fixture
def host(real_app, monkeypatch, tmp_path):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path / 'private'))
    return _cancel.host.__wrapped__(real_app, monkeypatch)


def _add(client, event_id, title='Undertaking form', instructions=INSTRUCTIONS, pdf=PDF,
         name='Undertaking form.pdf'):
    from io import BytesIO
    data = {'title': title, 'instructions': instructions}
    if pdf is not None:
        data['pdf'] = (BytesIO(pdf), name)
    return client.post(f'/coordinator/registrations/{event_id}/documents', data=data,
                       content_type='multipart/form-data')


def _docs(h, event_id):
    return h['db'].collection('events').document(event_id).get().to_dict().get('documents') or []


def _student(h, email):
    _user(h['db'], email, 'Student', name='Dee Doc')
    return _login(h['app'], email, 'Student')


def _flashes(client):
    with client.session_transaction() as s:
        return [m for _, m in s.get('_flashes', [])]


# ── Criterion 1: the SPOC adds instructions and a PDF; leads are told ───────

def test_the_spoc_adds_instructions_and_a_pdf_and_each_lead_is_told(host):
    h = host
    event_id = h['event']()
    _, lead, _ = h['register'](event_id)
    page = h['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'id="documents"' in page and 'data-document-form' in page and 'enctype="multipart/form-data"' in page

    resp = _add(h['owner'], event_id)
    assert resp.status_code == 302 and resp.headers['Location'].endswith('#documents')
    [doc] = _docs(h, event_id)
    assert doc['title'] == 'Undertaking form' and doc['instructions'] == INSTRUCTIONS
    assert doc['pdf_key'] and doc['pdf_name'] == 'Undertaking form.pdf' and doc['pdf_size'] == len(PDF)

    page = h['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert f'data-document="{doc["id"]}"' in page and 'room 204' in page
    notices = [n.to_dict() for n in h['db'].collection('notifications_v2').stream()
               if n.to_dict().get('user_email') == lead and n.to_dict().get('type') == 'event_document']
    assert len(notices) == 1 and 'Undertaking form' in notices[0]['title']
    assert any(a.to_dict().get('action') == 'EVENT_DOCUMENT_ADDED' for a in h['db'].collection('audit_log').stream())


# ── Criterion 2: instructions only, or a PDF only; refusals ─────────────────

def test_instructions_only_or_a_pdf_only_and_what_is_refused(host):
    h = host
    event_id = h['event']()
    _add(h['owner'], event_id, title='Reporting time', pdf=None)
    _add(h['owner'], event_id, title='Rules', instructions='', name='rules.pdf')
    only_text, only_pdf = _docs(h, event_id)
    assert only_text['instructions'] and not only_text['pdf_key']
    assert only_pdf['pdf_key'] and not only_pdf['instructions']

    _add(h['owner'], event_id, title='Empty', instructions='', pdf=None)
    _add(h['owner'], event_id, title='', instructions='Something')
    _add(h['owner'], event_id, title='Not a PDF', pdf=b'MZ\x90\x00 an exe', name='form.pdf')
    msgs = _flashes(h['owner'])
    assert "Type the instructions, choose a PDF, or both." in msgs
    assert any('Give the document a title' in m for m in msgs)
    assert any("That file isn't a PDF" in m for m in msgs)
    assert len(_docs(h, event_id)) == 2


# ── Criterion 3: the lead and the members see it and download the PDF ──────

def test_the_lead_and_members_see_the_instructions_and_download_the_pdf(host):
    h = host
    event_id = h['event']()
    _, lead, mate = h['register'](event_id, team_name='Doc Team')
    _add(h['owner'], event_id)
    [doc] = _docs(h, event_id)
    url = f'/participant/event/{event_id}/document/{doc["id"]}'
    for person in (lead, mate):
        client = _student(h, person)
        dash = client.get('/participant/dashboard').get_data(as_text=True)
        assert 'data-event-documents' in dash and 'id="event-documents"' in dash
        i = dash.index(f'data-event-document="{doc["id"]}"')
        card = dash[i:dash.index('</li>', i)]
        assert 'Undertaking form' in card and 'room 204' in card and f'href="{url}"' in card
        resp = client.get(url)
        assert resp.status_code == 200 and resp.data == PDF and resp.mimetype == 'application/pdf'
        assert 'attachment; filename="Undertaking form.pdf"' in resp.headers['Content-Disposition']
        assert resp.headers['Cache-Control'] == 'private, no-store'


# ── Criterion 4: nobody else downloads it; a cancelled team neither ─────────

def test_others_cannot_download_or_see_it_and_a_cancelled_team_loses_it(host):
    h = host
    event_id = h['event']()
    reg_id, lead, _ = h['register'](event_id)
    _add(h['owner'], event_id)
    [doc] = _docs(h, event_id)
    url = f'/participant/event/{event_id}/document/{doc["id"]}'

    stranger = _student(h, f"{_unique('stranger')}@test.edu")
    assert stranger.get(url).status_code == 403
    assert 'data-event-documents' not in stranger.get('/participant/dashboard').get_data(as_text=True)
    assert h['app'].test_client().get(url).status_code in (302, 401)   # not logged in
    assert h['owner'].get(url).status_code == 200                       # the event's staff
    assert _student(h, lead).get(f'/participant/event/{event_id}/document/nope').status_code == 404

    h['cancel'](h['owner'], event_id, reg_id, 'Duplicate team')
    client = _student(h, lead)
    assert client.get(url).status_code == 403
    assert 'data-event-documents' not in client.get('/participant/dashboard').get_data(as_text=True)


# ── Criterion 5: only the hosting SPOC adds and removes ─────────────────────

def test_only_the_hosting_spoc_adds_and_removes(host):
    h = host
    db, flask_app = h['db'], h['app']
    event_id = h['event']()
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    other_c = _login(flask_app, other, 'ClubSPOC')
    assert _add(other_c, event_id).status_code == 403
    assert _docs(h, event_id) == []

    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(event_id).update({'coordinators': [coord]})
    coord_c = _login(flask_app, coord, 'EventCoordinator')
    _add(h['owner'], event_id)
    [doc] = _docs(h, event_id)
    page = coord_c.get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert f'data-document="{doc["id"]}"' in page and 'data-document-form' not in page

    remove = f'/coordinator/registrations/{event_id}/documents/{doc["id"]}/remove'
    assert other_c.post(remove).status_code == 403 and coord_c.post(remove).status_code == 403
    assert len(_docs(h, event_id)) == 1
    resp = h['owner'].post(remove)
    assert resp.status_code == 302 and _docs(h, event_id) == []
    assert any(a.to_dict().get('action') == 'EVENT_DOCUMENT_REMOVED' for a in db.collection('audit_log').stream())


# ── Criterion 6: the download name is safe ──────────────────────────────────

def test_an_odd_file_name_is_made_safe():
    import services_event_documents as docs
    assert docs.safe_name('../../evil".pdf') == 'evil.pdf'
    assert docs.safe_name('C:\\forms\\under taking') == 'under taking.pdf'
    assert docs.safe_name('') == 'document.pdf'
