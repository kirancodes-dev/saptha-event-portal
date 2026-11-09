"""
tests/test_certificate_design.py — UPG-206 on the real database layer: the
organiser's own certificate design. Who may upload it and which files are
accepted; the stored file is private; placement in percentages works at any
image size; what the issued PDF says and where (name, number, team, long,
marked-up and Kannada names, the QR's link and corner); no signatory needed
for the design's type while other types still need one; certificates keep
the design they were issued with; the preview uses the longest name; and the
placement page in headless Chromium.
"""
import io
import json

import pytest
from PIL import Image, ImageDraw

import certificate_pdf
import services_certificate_design as design
import services_certificate_runs as runs
import services_certificates as certs
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils_storage import get_private

MM = 72 / 25.4


def artwork(size=(3508, 2480), fmt='PNG', colour=(250, 246, 235)):
    """A plain certificate design: a border and a title band, nothing where the name goes."""
    image = Image.new('RGB', size, colour)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rectangle([w // 40, h // 40, w - w // 40, h - h // 40], outline=(12, 18, 64), width=max(2, w // 300))
    draw.rectangle([w // 4, h // 8, 3 * w // 4, h // 5], fill=(201, 160, 32))
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def pdf_design(pages=1, portrait=False):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    size = A4 if portrait else landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    for i in range(pages):
        c.rect(20, 20, size[0] - 40, size[1] - 40)
        c.drawString(100, size[1] - 100, f'Certificate design page {i + 1}')
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique('des' + k)}@test.edu" for k in ('owner', 'other', 'coord', 'student')}
    for key, role in (('owner', 'ClubSPOC'), ('other', 'ClubSPOC'), ('coord', 'EventCoordinator'), ('student', 'Student')):
        _user(db, people[key], role)
    owner = _login(flask_app, people['owner'], 'ClubSPOC')

    def event(**fields):
        event_id = _create_event(owner, db, _unique('Designed Event'), '2031-08-08', team=True)
        db.collection('events').document(event_id).update(dict({
            'status': 'completed', 'staff': [{'name': 'Cora', 'email': people['coord'], 'role': 'EventCoordinator'}]},
            **fields))
        return event_id

    def person(event_id, name, team='', **fields):
        email = f"{_unique('p')}@test.edu"
        db.collection('registrations').document(_unique('REG')).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': email, 'lead_usn': '1SG22CS042',
            'status': 'Confirmed', 'attendance': 'Present', 'team_name': team or 'Individual'}, **fields))
        return email
    clients = {'owner': owner, 'other': _login(flask_app, people['other'], 'ClubSPOC'),
               'coord': _login(flask_app, people['coord'], 'EventCoordinator'),
               'student': _login(flask_app, people['student'], 'Student')}
    return {'app': flask_app, 'db': db, 'people': people, 'clients': clients, 'event': event, 'person': person}


def _upload(client, event_id, data, filename='design.png'):
    return client.post(f'/certificates/events/{event_id}/design', data={'design': (io.BytesIO(data), filename)},
                       content_type='multipart/form-data', follow_redirects=True)


def _event(d, event_id):
    return dict(d['db'].collection('events').document(event_id).get().to_dict() or {}, id=event_id)


def _settings(client, event_id, **values):
    form = {'name_x': 10, 'name_y': 45, 'name_w': 80, 'name_size': 40, 'name_color': '#112233',
            'name_align': 'center', 'name_bold': '1', 'qr_corner': 'br'}
    form.update(values)
    return client.post(f'/certificates/events/{event_id}/design/settings', data=form, follow_redirects=True)


def _issue(d, event_id, only=('participation',)):
    return certs.issue_event(d['db'], event_id, d['people']['owner'], only=list(only) if only else None)


def _cert(event_id, email):
    return next(c for c in certs.for_event(event_id) if c['email'] == email and c['cert_type'] == 'participation')


def _boxes(pdf, text):
    """The text's (left, bottom, right, top) in points on the first page, from the PDF itself."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    try:
        tp = doc[0].get_textpage()
        whole = tp.get_text_range()
        start = whole.find(text)
        assert start >= 0, (text, whole)
        boxes = [tp.get_charbox(i) for i in range(start, start + len(text)) if not whole[i].isspace()]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    finally:
        doc.close()


def _images(pdf):
    """Every image on the first page: (left, bottom, right, top) in points."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    doc = pdfium.PdfDocument(pdf)
    try:
        return [obj.get_bounds() for obj in doc[0].get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE])]
    finally:
        doc.close()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_only_editors_upload_bad_files_are_refused_and_the_design_is_private(site):
    d = site
    event_id = d['event']()
    for who in ('other', 'student', 'coord'):
        assert _upload(d['clients'][who], event_id, artwork()).status_code == 403, who
    assert design.get(_event(d, event_id)) is None

    gif = io.BytesIO()
    Image.new('RGB', (3508, 2480), 'white').save(gif, format='GIF')
    refusals = {
        'gif': (gif.getvalue(), 'design.gif', 'Upload the design as a PNG, JPG or one-page PDF'),
        'big': (b'\x89PNG' + b'0' * (6 * 1024 * 1024), 'big.png', '5 MB or smaller'),
        'two pages': (pdf_design(pages=2), 'two.pdf', 'Upload a one-page PDF'),
        'square': (artwork(size=(2000, 2000)), 'square.png', 'must be A4 shape'),
        'not an image': (b'hello', 'x.png', 'Upload the design as a PNG, JPG or one-page PDF'),
    }
    for label, (data, name, message) in refusals.items():
        page = _upload(d['clients']['owner'], event_id, data, name).get_data(as_text=True)
        assert message in page, label
        assert design.get(_event(d, event_id)) is None, label

    accepted = [(artwork(), 'a.png', 'landscape'), (artwork(fmt='JPEG'), 'a.jpg', 'landscape'),
                (pdf_design(), 'a.pdf', 'landscape'), (artwork(size=(2480, 3508)), 'p.png', 'portrait'),
                (pdf_design(portrait=True), 'p.pdf', 'portrait')]
    for data, name, orientation in accepted:
        page = _upload(d['clients']['owner'], event_id, data, name).get_data(as_text=True)
        assert 'Design uploaded' in page, name
        saved = design.get(_event(d, event_id))
        assert saved['orientation'] == orientation, name
        stored = get_private(saved['image_key'])
        assert Image.open(io.BytesIO(stored)).format == 'JPEG'
        assert not saved['image_key'].startswith('static')

    low = _upload(d['clients']['owner'], event_id, artwork(size=(1169, 827))).get_data(as_text=True)
    assert 'may print blurry' in low

    url = f'/certificates/events/{event_id}/design.jpg'
    assert d['clients']['owner'].get(url).status_code == 200
    assert d['clients']['owner'].get(url).headers['Cache-Control'] == 'private, no-store'
    for who in ('other', 'student'):
        assert d['clients'][who].get(url).status_code == 403, who
    assert d['app'].test_client().get(url).status_code in (302, 401)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_settings_are_percentages_and_place_the_name_alike_at_any_image_size(site):
    d = site
    places = []
    for width in (3508, 1754):
        event_id = d['event']()
        email = d['person'](event_id, 'Asha Rao')
        _upload(d['clients']['owner'], event_id, artwork(size=(width, round(width / design.A4_RATIO))))
        assert 'Placement saved' in _settings(d['clients']['owner'], event_id, name_x=15, name_y=40, name_w=70,
                                              name_size=36).get_data(as_text=True)
        saved = design.get(_event(d, event_id))['fields']['name']
        assert (saved['x'], saved['y'], saved['w'], saved['size']) == (15, 40, 70, 36)
        _issue(d, event_id)
        places.append(_boxes(get_private(_cert(event_id, email)['pdf_key']), 'Asha Rao'))
    for a, b in zip(*places):
        assert abs(a - b) < 1 * MM
    left, bottom, right, top = places[0]
    W, H = 841.89, 595.28
    assert abs((left + right) / 2 - W * (0.15 + 0.35)) < 3 * MM          # centred in its box
    assert abs((bottom + top) / 2 - H * (1 - 0.40)) < 4 * MM             # on its centre line

    # Out-of-range values are clamped, not stored as given
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())
    _settings(d['clients']['owner'], event_id, name_x=500, name_y=-3, name_w=1, name_size='abc', name_color='red')
    saved = design.get(_event(d, event_id))['fields']['name']
    assert saved['w'] == 5 and saved['x'] == 95 and saved['y'] == 2 and saved['size'] == 40
    assert saved['color'] == '#112233' or saved['color'].startswith('#')


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_pdf_says_who_with_the_team_number_and_a_qr_in_its_corner(site, monkeypatch):
    d = site
    monkeypatch.setitem(d['app'].config, 'BASE_URL', 'https://events.example.edu')
    monkeypatch.setenv('BASE_URL', 'https://events.example.edu')
    links = []
    real_qr = certificate_pdf._qr
    monkeypatch.setattr(certificate_pdf, '_qr', lambda url: links.append(url) or real_qr(url))
    event_id = d['event']()
    long_name = ('Venkata Lakshmi Narasimha Subramanya ' * 4)[:120]
    people = {'plain': d['person'](event_id, 'Meera Iyer', team='Code Ninjas'),
              'long': d['person'](event_id, long_name, team='Code Ninjas'),
              'markup': d['person'](event_id, '<b>Ann</b> & Co', team='Code Ninjas')}
    _upload(d['clients']['owner'], event_id, artwork())
    _settings(d['clients']['owner'], event_id, name_x=20, name_w=60, team_on='1', team_x=25, team_y=60, team_w=50,
              team_size=18, qr_corner='tl')
    _issue(d, event_id)

    W, H = 841.89, 595.28
    plain = _cert(event_id, people['plain'])
    pdf = get_private(plain['pdf_key'])
    text = certificate_pdf.text_of(pdf)
    assert 'Meera Iyer' in text and 'Code Ninjas' in text and plain['number'] in text
    qr = [box for box in _images(pdf) if box[2] - box[0] < W / 2]       # the design is full page; the QR small
    assert len(qr) == 1
    left, bottom, right, top = qr[0]
    assert left < 15 * MM and top > H - 15 * MM                          # top left, as chosen
    assert f"https://events.example.edu/verify/{plain['number']}" in links

    box_left, box_right = W * 0.20, W * 0.80
    l, _, r, _ = _boxes(get_private(_cert(event_id, people['long'])['pdf_key']), 'Venkata')
    whole = certificate_pdf.text_of(get_private(_cert(event_id, people['long'])['pdf_key']))
    assert 'Subramanya' in whole
    long_pdf = get_private(_cert(event_id, people['long'])['pdf_key'])
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(long_pdf)
    try:
        tp = doc[0].get_textpage()
        name_chars = [tp.get_charbox(i) for i in range(tp.count_chars())
                      if box_left - 40 < tp.get_charbox(i)[0] < box_right + 40 and tp.get_charbox(i)[1] > H * 0.3]
    finally:
        doc.close()
    assert name_chars and min(b[0] for b in name_chars) >= box_left - 1 and max(b[2] for b in name_chars) <= box_right + 1

    assert '<b>Ann</b> & Co' in certificate_pdf.text_of(get_private(_cert(event_id, people['markup'])['pdf_key']))

    kannada = certificate_pdf.render_design(number='SE-TEST-0000-0000-0', name='ಶ್ರೀನಿವಾಸ ಕೃಷ್ಣಮೂರ್ತಿ', data={},
                                            design=design.get(_event(d, event_id)),
                                            image=artwork(size=(1169, 827)), verify_url='https://x/verify/1')
    assert b'NotoSansKannada' in kannada


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_design_needs_no_signatory_but_other_types_still_do(site):
    d = site
    event_id = d['event']()
    email = d['person'](event_id, 'Ravi Kumar')
    assert runs.ready_to_issue(_event(d, event_id))                      # no design, no signatory: refused
    _upload(d['clients']['owner'], event_id, artwork())
    event = _event(d, event_id)
    assert runs.ready_to_issue(event) is None
    assert runs.ready_to_issue(event, ['winner']) == "Add at least one certificate signatory (name, title and signature) before issuing certificates."
    with pytest.raises(certs.CertificateError, match='signatory'):
        _issue(d, event_id, only=['winner'])

    counts = _issue(d, event_id, only=None)                              # everything owed: only the design's type
    assert counts['issued'] == 1 and counts['failed'] == 0
    assert [c['cert_type'] for c in certs.for_event(event_id)] == ['participation']
    assert _cert(event_id, email)['data']['design']['sha256'] == design.get(event)['sha256']

    page = d['clients']['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Your own design is used for every Certificate of Participation' in page
    assert 'aria-describedby="issue-problem"' not in page               # the bulk button is enabled
    run = runs.start(d['db'], event_id, d['people']['owner'])
    assert run['total'] == 1                                             # the coordinator's certificate isn't planned


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_issued_certificates_keep_their_design_and_changes_are_audited(site):
    d = site
    event_id = d['event']()
    early = d['person'](event_id, 'Early Bird')
    _upload(d['clients']['owner'], event_id, artwork(colour=(255, 255, 255)))
    _settings(d['clients']['owner'], event_id, name_y=40)
    _issue(d, event_id)
    first = _cert(event_id, early)

    _upload(d['clients']['owner'], event_id, artwork(colour=(230, 240, 255)))
    _settings(d['clients']['owner'], event_id, name_y=60)
    late = d['person'](event_id, 'Late Comer')
    _issue(d, event_id)
    second = _cert(event_id, late)

    assert first['data']['design']['sha256'] != second['data']['design']['sha256']
    assert first['data']['design']['fields']['name']['y'] == 40 and second['data']['design']['fields']['name']['y'] == 60
    assert _cert(event_id, early)['pdf_sha256'] == first['pdf_sha256']            # not redrawn
    early_y = _boxes(get_private(first['pdf_key']), 'Early Bird')[1]
    late_y = _boxes(get_private(second['pdf_key']), 'Late Comer')[1]
    assert early_y > late_y + 50                                                    # 40% vs 60% from the top
    assert get_private(first['data']['design']['image_key'])                        # the old file is kept

    d['clients']['owner'].post(f'/certificates/events/{event_id}/design/delete')
    assert design.get(_event(d, event_id)) is None
    actions = [a.to_dict().get('action') for a in d['db'].collection('audit_log').stream()
               if event_id in json.dumps(a.to_dict(), default=str)]
    assert {'CERT_DESIGN_UPLOADED', 'CERT_DESIGN_CHANGED', 'CERT_DESIGN_REMOVED'} <= set(actions)


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_the_preview_uses_the_longest_registered_name(site, monkeypatch):
    d = site
    names = []
    real = certificate_pdf.render_design
    monkeypatch.setattr(certificate_pdf, 'render_design', lambda **kw: names.append(kw['name']) or real(**kw))
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())
    response = d['clients']['owner'].get(f'/certificates/events/{event_id}/preview.png')
    assert response.status_code == 200 and response.mimetype == 'image/png'
    assert names[-1] == 'Sample Recipient'

    d['person'](event_id, 'Al Li')
    d['person'](event_id, 'Bhagyalakshmi Ramachandran Iyengar')
    d['person'](event_id, 'Chen Wu')
    d['clients']['owner'].get(f'/certificates/events/{event_id}/preview.png')
    assert names[-1] == 'Bhagyalakshmi Ramachandran Iyengar'
    page = d['clients']['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Bhagyalakshmi Ramachandran Iyengar' in page


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_the_placement_page_fits_and_dragging_or_typing_moves_the_box(site, tmp_path):
    import os
    from tests.headless import chromium, live_server
    from tests.test_phone_journey import DESKTOP, _check, _login_in_browser, _routes
    d = site
    event_id = d['event']()
    d['person'](event_id, 'Drag Test Person')
    _upload(d['clients']['owner'], event_id, artwork())
    d['shots'] = os.environ.get('CERT_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(d['shots'], exist_ok=True)
    problems = []
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            base = server.url
            ctx = browser.new_context(viewport=DESKTOP)
            _routes(ctx, base)
            page = ctx.new_page()
            _login_in_browser(page, base, d['people']['owner'], 'ClubSPOC')
            page.goto(f'{base}/certificates/events/{event_id}#design')
            page.wait_for_selector('#cdStage img')
            _check(page, d, 'design-placement', problems)

            page.set_viewport_size(DESKTOP)
            page.wait_for_timeout(200)
            box = page.locator('[data-field="name"]')
            box.scroll_into_view_if_needed()
            page.wait_for_timeout(100)
            before = box.bounding_box()
            x0 = float(page.input_value('#name_x'))
            y0 = float(page.input_value('#name_y'))
            page.mouse.move(before['x'] + 30, before['y'] + before['height'] / 2)
            page.mouse.down()
            page.mouse.move(before['x'] + 90, before['y'] + before['height'] / 2 + 40, steps=8)
            page.mouse.up()
            assert float(page.input_value('#name_x')) > x0 + 2
            assert float(page.input_value('#name_y')) > y0 + 2

            page.fill('#name_y', '20')
            page.dispatch_event('#name_y', 'input')
            stage = page.locator('#cdStage').bounding_box()
            moved = box.bounding_box()
            centre = (moved['y'] + moved['height'] / 2 - stage['y']) / stage['height'] * 100
            assert abs(centre - 20) < 2

            with page.expect_navigation():
                page.click('#cdForm button[type=submit]')
            assert 'Placement saved' in page.content()
            assert design.get(_event(d, event_id))['fields']['name']['y'] == 20
    finally:
        browser.close()
        p.stop()
    assert problems == []
