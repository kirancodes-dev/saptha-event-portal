"""
tests/test_certificate_signatories.py — UPG-123 on the real database layer:
each event's signatories (who may manage them, which images are accepted),
signature images kept private, no issuing without a signature, signatories
fixed on each certificate as issued, the preview, branding from settings, and
what the PDF says (name, event, number; long, marked-up and Kannada names; a
random number; the QR code's link).
"""
import io
import json

import pytest
from PIL import Image, ImageDraw

import certificate_pdf
import services_certificates as certs
import services_signatories as sigs
from tests.test_integration_flow import _create_event, _login, _unique, _user


def signature(fmt='PNG', size=(800, 300), background=(255, 255, 255), ink=(10, 20, 80)):
    image = Image.new('RGB', size, background)
    draw = ImageDraw.Draw(image)
    draw.line([(150, 200), (300, 90), (420, 210), (600, 100)], fill=ink, width=8)
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique('sig' + k)}@test.edu" for k in ('owner', 'other', 'coord', 'student')}
    for key, role in (('owner', 'ClubSPOC'), ('other', 'ClubSPOC'), ('coord', 'EventCoordinator'), ('student', 'Student')):
        _user(db, people[key], role)
    owner = _login(flask_app, people['owner'], 'ClubSPOC')

    def event(**fields):
        event_id = _create_event(owner, db, _unique('Signed Event'), '2031-09-09', team=False)
        db.collection('events').document(event_id).update(dict({
            'status': 'completed', 'staff': [{'name': 'Cora', 'email': people['coord'], 'role': 'EventCoordinator'}]},
            **fields))
        return event_id
    clients = {'owner': owner, 'other': _login(flask_app, people['other'], 'ClubSPOC'),
               'coord': _login(flask_app, people['coord'], 'EventCoordinator'),
               'student': _login(flask_app, people['student'], 'Student')}
    return {'app': flask_app, 'db': db, 'people': people, 'clients': clients, 'event': event}


def _add(client, event_id, name='Dr. A. Kumar', title='Principal', image=None, filename='sig.png'):
    return client.post(f'/certificates/events/{event_id}/signatories', data={
        'name': name, 'title': title, 'signature': (io.BytesIO(image if image is not None else signature()), filename)},
        content_type='multipart/form-data', follow_redirects=True)


def _listing(d, event_id):
    return sigs.listing(d['db'], event_id)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_only_editors_manage_signatories_and_bad_images_are_refused(site):
    d = site
    event_id = d['event']()
    for who in ('other', 'student', 'coord'):
        assert _add(d['clients'][who], event_id).status_code == 403, who
    assert _listing(d, event_id) == []

    refusals = {
        'gif': (signature('GIF'), 'Upload the signature as a PNG or JPG image'),
        'big': (b'\x89PNG' + b'0' * (2 * 1024 * 1024), '1 MB or smaller'),
        'text': (b'not an image at all', 'Upload the signature as a PNG or JPG image'),
        'dark': (signature(background=(30, 30, 30), ink=(250, 250, 250)), 'white or transparent background'),
    }
    for label, (image, message) in refusals.items():
        page = _add(d['clients']['owner'], event_id, image=image).get_data(as_text=True)
        assert message in page, label
    assert _listing(d, event_id) == []

    for i, fmt in enumerate(('PNG', 'JPEG', 'PNG')):
        page = _add(d['clients']['owner'], event_id, name=f'Signer {i}', image=signature(fmt)).get_data(as_text=True)
        assert f'Signer {i} added as a signatory' in page
    fourth = _add(d['clients']['owner'], event_id, name='One Too Many').get_data(as_text=True)
    assert 'at most 3 signatories' in fourth and len(_listing(d, event_id)) == 3

    # Reordering, removing and copying need edit_event too
    ids = [s['id'] for s in _listing(d, event_id)]
    own = d['event']()
    for who in ('other', 'student', 'coord'):
        client = d['clients'][who]
        assert client.post(f'/certificates/events/{event_id}/signatories/order',
                           data={f'order_{i}': str(3 - n) for n, i in enumerate(ids)}).status_code == 403, who
        assert client.post(f'/certificates/events/{event_id}/signatories/{ids[0]}/delete').status_code == 403, who
        assert client.post(f'/certificates/events/{own}/signatories/copy',
                           data={'source_event_id': event_id}).status_code == 403, who
    assert [s['id'] for s in _listing(d, event_id)] == ids and _listing(d, own) == []


def test_an_accepted_signature_is_trimmed_resized_and_transparent():
    png = sigs.process_signature(signature(size=(1600, 900)))
    image = Image.open(io.BytesIO(png))
    assert image.format == 'PNG' and image.mode == 'RGBA'
    assert image.size[0] <= 600 and image.size[1] <= 200
    assert image.getpixel((0, 0))[3] == 0 or image.getbbox() == (0, 0) + image.size   # trimmed to the ink
    transparent = Image.new('RGBA', (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(transparent).line([(20, 150), (380, 40)], fill=(0, 0, 0, 255), width=6)
    buf = io.BytesIO()
    transparent.save(buf, format='PNG')
    assert sigs.process_signature(buf.getvalue())                       # a transparent background is fine too


def test_reorder_remove_and_copy_from_an_own_event(site):
    d = site
    first, second = d['event'](), d['event']()
    for name in ('Left Person', 'Right Person'):
        _add(d['clients']['owner'], first, name=name)
    ids = {s['name']: s['id'] for s in _listing(d, first)}
    d['clients']['owner'].post(f'/certificates/events/{first}/signatories/order', data={
        f"order_{ids['Left Person']}": '2', f"order_{ids['Right Person']}": '1'})
    assert [s['name'] for s in _listing(d, first)] == ['Right Person', 'Left Person']

    resp = d['clients']['owner'].post(f'/certificates/events/{second}/signatories/copy', data={'source_event_id': first},
                                      follow_redirects=True)
    assert 'Copied 2 signatories' in resp.get_data(as_text=True)
    copied = _listing(d, second)
    assert [s['name'] for s in copied] == ['Right Person', 'Left Person']
    assert all(s['image_key'].startswith(f'signatures/{second}/') for s in copied)   # its own copy of each image

    other_event = _create_event(d['clients']['other'], d['db'], _unique('Not Yours'), '2031-09-10', team=False)
    assert d['clients']['owner'].post(f'/certificates/events/{first}/signatories/copy',
                                      data={'source_event_id': other_event}).status_code == 403
    d['clients']['owner'].post(f"/certificates/events/{first}/signatories/{ids['Left Person']}/delete")
    assert [s['name'] for s in _listing(d, first)] == ['Right Person']


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_signature_images_are_private(site):
    d = site
    event_id = d['event']()
    _add(d['clients']['owner'], event_id)
    [sig] = _listing(d, event_id)
    url = f"/certificates/events/{event_id}/signatories/{sig['id']}/image"
    for who in ('owner', 'coord'):
        resp = d['clients'][who].get(url)
        assert resp.status_code == 200 and resp.data[:4] == b'\x89PNG' and 'no-store' in resp.headers['Cache-Control']
    for who in ('other', 'student'):
        assert d['clients'][who].get(url).status_code == 403, who
    assert d['app'].test_client().get(url).status_code in (302, 401)
    import utils_storage
    assert 'static' not in utils_storage._private_local_path(sig['image_key']).split('instance')[0][-8:]
    assert '/static/' not in utils_storage._private_local_path(sig['image_key'])


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_no_certificate_without_a_signature(site):
    d = site
    event_id = d['event']()
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_name': 'Waiting Wren', 'lead_email': f"{_unique('wren')}@test.edu",
        'status': 'Confirmed', 'attendance': 'Present'})
    with pytest.raises(certs.CertificateError, match='Add at least one certificate signatory'):
        certs.issue_event(d['db'], event_id, d['people']['owner'])
    page = d['clients']['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Add at least one certificate signatory' in page
    _add(d['clients']['owner'], event_id)
    assert certs.issue_event(d['db'], event_id, d['people']['owner'])['issued'] >= 1


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_issued_certificates_keep_their_signatories_and_changes_are_audited(site):
    d = site
    event_id = d['event']()
    _add(d['clients']['owner'], event_id, name='Dr. Before', title='Principal')
    first = _unique('first')
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_name': 'Early Bird', 'lead_email': f'{first}@test.edu', 'status': 'Confirmed',
        'attendance': 'Present'})
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    [sig] = _listing(d, event_id)
    d['clients']['owner'].post(f"/certificates/events/{event_id}/signatories/{sig['id']}/delete")
    _add(d['clients']['owner'], event_id, name='Dr. After', title='Vice-Chancellor')
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_name': 'Late Comer', 'lead_email': f"{_unique('late')}@test.edu",
        'status': 'Confirmed', 'attendance': 'Present'})
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    signed = {c['name']: [s['name'] for s in c['data']['signatories']] for c in certs.for_event(event_id)
              if c['cert_type'] == 'participation'}
    assert signed == {'Early Bird': ['Dr. Before'], 'Late Comer': ['Dr. After']}
    early = next(c for c in certs.for_event(event_id) if c['name'] == 'Early Bird')
    from utils_storage import get_private
    assert 'Dr. Before' in certificate_pdf.text_of(get_private(early['pdf_key']))       # the file wasn't redrawn
    actions = [a.to_dict().get('action') for a in d['db'].collection('audit_log').stream()
               if event_id in json.dumps(a.to_dict(), default=str)]
    assert {'CERT_SIGNATORY_ADDED', 'CERT_SIGNATORY_REMOVED'} <= set(actions)


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_preview_shows_real_signatories_and_branding_comes_from_settings(site, monkeypatch, tmp_path):
    d = site
    event_id = d['event'](cert_style='modern')
    _add(d['clients']['owner'], event_id, name='Dr. Preview Person', title='Dean')
    resp = d['clients']['owner'].get(f'/certificates/events/{event_id}/preview.png')
    assert resp.status_code == 200 and resp.data[:4] == b'\x89PNG'
    assert d['clients']['student'].get(f'/certificates/events/{event_id}/preview.png').status_code == 403
    monkeypatch.setenv('COLLEGE_NAME', 'Example Institute of Technology')
    event = d['db'].collection('events').document(event_id).get().to_dict()
    sample = {'name': 'Sample Recipient', 'cert_type': 'participation'}
    pdf = certificate_pdf.render(number='SE-TEST-0000-0000-0', name='Sample Recipient', data=certs.wording(event, sample),
                                 cert_type='participation', signatories=_listing(d, event_id),
                                 verify_url='https://events.example.edu/verify/SE-TEST-0000-0000-0', issued_on='today')
    text = certificate_pdf.text_of(pdf)
    assert 'EXAMPLE INSTITUTE OF TECHNOLOGY' in text and 'Dr. Preview Person' in text and 'Dean' in text

    # The logo is the one named in settings (a file under static/)
    def red_pixels(pdf):
        image = Image.open(io.BytesIO(certificate_pdf.to_png(pdf, scale=0.5))).convert('RGB')
        raw = image.tobytes()
        return sum(1 for i in range(0, len(raw), 3) if raw[i] > 200 and raw[i + 1] < 40 and raw[i + 2] < 40)
    static = tmp_path / 'static'
    static.mkdir()
    Image.new('RGB', (230, 58), (255, 0, 0)).save(static / 'college-logo.png')
    monkeypatch.setattr(certificate_pdf, 'ROOT', str(tmp_path))
    args = dict(number='SE-TEST-0000-0000-0', name='Sample Recipient', data=certs.wording(event, sample),
                cert_type='participation', signatories=[], verify_url='https://e.example/verify/x', issued_on='today')
    monkeypatch.setenv('COLLEGE_LOGO_PATH', 'static/college-logo.png')
    assert certificate_pdf.branding()['logo'] == str(static / 'college-logo.png')
    assert red_pixels(certificate_pdf.render(**args)) > 1000
    monkeypatch.setenv('COLLEGE_LOGO_PATH', '../outside.png')            # only files under static/
    assert certificate_pdf.branding()['logo'] == '' and red_pixels(certificate_pdf.render(**args)) < 50


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def _pdf(name, monkeypatch=None, **data):
    wording = dict({'title': 'Certificate of Participation', 'phrase': 'for participating in',
                    'event_title': 'Quantum Computing Bootcamp', 'date': '2031-09-09'}, **data)
    return certificate_pdf.render(number='SE-ABCD-EFGH-JKMN-P', name=name, data=wording, cert_type='participation',
                                  signatories=[{'id': 'x', 'name': 'Dr. A. Kumar', 'title': 'Principal', 'order': 1}],
                                  verify_url='https://events.example.edu/verify/SE-ABCD-EFGH-JKMN-P', issued_on='9 September 2031')


def test_the_pdf_says_who_what_and_which_number():
    text = certificate_pdf.text_of(_pdf('Ananya Rao'))
    assert 'Ananya Rao' in text and 'Quantum Computing Bootcamp' in text and 'SE-ABCD-EFGH-JKMN-P' in text
    assert 'https://events.example.edu/verify/SE-ABCD-EFGH-JKMN-P' in text


def test_long_names_fit_and_markup_is_printed_as_text():
    long_name = ('Venkata Subramanya Lakshmi Narasimha Srinivasa Raghavendra Krishnamurthy '
                 'Chandrasekhara Ramachandra Bhattacharya Iyengar')[:120]
    from reportlab.lib.pagesizes import A4, landscape
    width = landscape(A4)[0]
    size, lines = certificate_pdf.name_lines(long_name, width - 180)
    assert len(lines) == 2 and size >= 14 and ' '.join(lines) == long_name
    assert all(certificate_pdf.text_width(line, size, bold=True) <= width - 180 for line in lines)
    short_size, short_lines = certificate_pdf.name_lines('Ananya Rao', width - 180)
    assert short_lines == ['Ananya Rao'] and short_size == 34
    assert long_name in ' '.join(certificate_pdf.text_of(_pdf(long_name)).split())
    marked = certificate_pdf.text_of(_pdf('<b>Bold</b> & <script>x</script>'))
    assert '<b>Bold</b> & <script>x</script>' in marked


def test_a_kannada_name_uses_the_kannada_font():
    pdf = _pdf('ಶ್ರೀನಿವಾಸ ಕೃಷ್ಣಮೂರ್ತಿ')
    assert b'NotoSansKannada' in pdf
    assert [s for s, _ in certificate_pdf.runs('ಶ್ರೀನಿವಾಸ Rao')] == ['kannada', 'latin']
    assert [s for s, _ in certificate_pdf.runs('श्रीनिवास')] == ['devanagari']


def test_the_number_is_random_and_the_qr_links_to_verification(site, monkeypatch):
    d = site
    monkeypatch.setitem(d['app'].config, 'BASE_URL', 'https://events.example.edu')
    monkeypatch.setenv('BASE_URL', 'https://events.example.edu')
    links = []
    real_qr = certificate_pdf._qr
    monkeypatch.setattr(certificate_pdf, '_qr', lambda url: links.append(url) or real_qr(url))
    event_id = d['event']()
    _add(d['clients']['owner'], event_id)
    for name in ('Same Name', 'Same Name'):
        d['db'].collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'lead_name': name, 'lead_email': f"{_unique('same')}@test.edu",
            'status': 'Confirmed', 'attendance': 'Present'})
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    issued = [c for c in certs.for_event(event_id) if c['cert_type'] == 'participation']
    assert len({c['number'] for c in issued}) == 2                      # same name, different random numbers
    assert sorted(links) == sorted(f"https://events.example.edu/verify/{c['number']}" for c in issued)
