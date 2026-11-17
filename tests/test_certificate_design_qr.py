"""
tests/test_certificate_design_qr.py — UPG-315: on the organiser's own design,
the QR code can go in a box the organiser places (the design's own "scan to
verify" box) at the size they choose, with nothing printed around it; the
certificate number then goes in a box of its own; the corners work as
before; settings are clamped; and the QR box drags and resizes on the
placement page.
"""
import io

from PIL import Image, ImageDraw

import certificate_pdf
import services_certificate_design as design
from tests.test_certificate_design import (MM, _boxes, _cert, _event, _images, _issue, _settings, _upload,  # noqa: F401
                                           artwork, site)
from utils_storage import get_private

W, H = 841.89, 595.28
# The owner's Sapthahacks'26 design: a white box on the right, 81.5-94.5% across, 44-62% down
BOX = (81.5, 44.0, 94.5, 62.0)
PLACED = {'qr_corner': 'place', 'qr_x': 82.2, 'qr_y': 44.8, 'qr_size': 11.8}


def boxed_artwork(size=(3508, 2480)):
    """A design with its own white QR box, like the owner's."""
    image = Image.open(io.BytesIO(artwork(size=size)))
    w, h = size
    ImageDraw.Draw(image).rectangle([w * BOX[0] / 100, h * BOX[1] / 100, w * BOX[2] / 100, h * BOX[3] / 100],
                                    fill=(255, 255, 255), outline=(200, 200, 200))
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()


def _paths(pdf):
    """How many drawn shapes (rectangles, lines) are on the first page."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    doc = pdfium.PdfDocument(pdf)
    try:
        return len(list(doc[0].get_objects(filter=[raw.FPDF_PAGEOBJ_PATH])))
    finally:
        doc.close()


def _small_images(pdf):
    return [b for b in _images(pdf) if b[2] - b[0] < W / 2]       # the design is full page


# 1. The QR in the design's own box, at that size, alone; a corner as before
def test_the_qr_goes_in_the_box_the_organiser_placed(site, monkeypatch):  # noqa: F811
    d = site
    monkeypatch.setenv('BASE_URL', 'https://events.example.edu')
    monkeypatch.setitem(d['app'].config, 'BASE_URL', 'https://events.example.edu')
    links = []
    real_qr = certificate_pdf._qr
    monkeypatch.setattr(certificate_pdf, '_qr', lambda url: links.append(url) or real_qr(url))
    event_id = d['event']()
    email = d['person'](event_id, 'Meera Iyer')
    _upload(d['clients']['owner'], event_id, boxed_artwork())
    assert 'Placement saved' in _settings(d['clients']['owner'], event_id, **PLACED).get_data(as_text=True)
    assert design.get(_event(d, event_id))['qr'] == {'corner': 'place', 'x': 82.2, 'y': 44.8, 'size': 11.8}
    _issue(d, event_id)
    cert = _cert(event_id, email)
    pdf = get_private(cert['pdf_key'])

    (left, bottom, right, top), = _small_images(pdf)
    assert abs((right - left) - W * 0.118) < 0.5 and abs((top - bottom) - W * 0.118) < 0.5   # square, 11.8% wide
    assert abs(left - W * 0.822) < 0.5 and abs(top - H * (1 - 0.448)) < 0.5
    assert left >= W * BOX[0] / 100 and right <= W * BOX[2] / 100                # inside the design's box
    assert top <= H * (1 - BOX[1] / 100) and bottom >= H * (1 - BOX[3] / 100)
    assert f"https://events.example.edu/verify/{cert['number']}" in links
    text = certificate_pdf.text_of(pdf)
    assert 'Meera Iyer' in text and cert['number'] not in text and 'No.' not in text
    assert _paths(pdf) == 0                                                       # no white patch

    # A corner still prints with its patch and the number under it
    other = d['event']()
    email = d['person'](other, 'Ravi Kumar')
    _upload(d['clients']['owner'], other, boxed_artwork())
    _settings(d['clients']['owner'], other, qr_corner='br')
    _issue(d, other)
    cert = _cert(other, email)
    pdf = get_private(cert['pdf_key'])
    (left, bottom, right, top), = _small_images(pdf)
    assert right > W - 15 * MM and bottom < 20 * MM and abs((right - left) - certificate_pdf.QR_SIZE) < 0.5
    assert f"No. {cert['number']}" in certificate_pdf.text_of(pdf) and _paths(pdf) >= 1


# 2. The certificate number in a box of its own, off by default
def test_the_number_prints_in_its_own_box_when_switched_on(site):  # noqa: F811
    d = site
    event_id = d['event']()
    email = d['person'](event_id, 'Asha Rao')
    _upload(d['clients']['owner'], event_id, boxed_artwork())
    fields = design.get(_event(d, event_id))['fields']
    assert fields['number']['on'] is False
    _settings(d['clients']['owner'], event_id, number_on='1', number_x=80, number_y=66, number_w=16,
              number_size=8, **PLACED)
    _issue(d, event_id)
    cert = _cert(event_id, email)
    left, bottom, right, top = _boxes(get_private(cert['pdf_key']), cert['number'])
    assert W * 0.80 - 1 <= left and right <= W * 0.96 + 1                        # in its box
    assert abs((bottom + top) / 2 - H * (1 - 0.66)) < 3 * MM


# 3. Clamped settings; an older design keeps its corner
def test_qr_settings_are_clamped_and_older_designs_keep_their_corner(site):  # noqa: F811
    d = site
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())
    _settings(d['clients']['owner'], event_id, qr_corner='place', qr_x=99, qr_y=99, qr_size=80)
    qr = design.get(_event(d, event_id))['qr']
    assert qr['size'] == 30 and qr['x'] == 70 and abs(qr['y'] - (100 - 30 * 297 / 210)) < 0.01
    side, x, y = certificate_pdf.placed_qr(qr, W, H)
    assert x + side <= W + 0.01 and y >= -0.01                                    # on the page
    _settings(d['clients']['owner'], event_id, qr_corner='place', qr_size=1)
    assert design.get(_event(d, event_id))['qr']['size'] == 5
    _settings(d['clients']['owner'], event_id, qr_corner='middle')                # not a choice: kept
    assert design.get(_event(d, event_id))['qr']['corner'] == 'place'

    # A design saved before UPG-315 (a corner only, no number box) is unchanged
    stored = dict(d['db'].collection('events').document(event_id).get().to_dict()['cert_design'])
    stored['qr'] = {'corner': 'tl'}
    stored['fields'] = {k: v for k, v in stored['fields'].items() if k != 'number'}
    d['db'].collection('events').document(event_id).update({'cert_design': stored})
    old = design.get(_event(d, event_id))
    assert old['qr']['corner'] == 'tl' and old['fields']['number']['on'] is False
    pdf = certificate_pdf.render_design(number='SE-TEST-0000-0000-0', name='Old Design', data={},
                                        design={'orientation': 'landscape', 'fields': stored['fields'],
                                                'qr': {'corner': 'tl'}},
                                        image=artwork(size=(1169, 827)), verify_url='https://x/verify/1')
    (left, bottom, right, top), = _small_images(pdf)
    assert left < 15 * MM and top > H - 15 * MM and 'No. SE-TEST-0000-0000-0' in certificate_pdf.text_of(pdf)


# 4. On the placement page the QR box drags and resizes, and the form follows (headless)
def test_the_qr_box_drags_and_resizes_on_the_placement_page(site, tmp_path):  # noqa: F811
    import os
    from tests.headless import chromium, live_server
    from tests.test_phone_journey import DESKTOP, _check, _login_in_browser, _routes
    d = site
    event_id = d['event']()
    d['person'](event_id, 'Drag Test Person')
    _upload(d['clients']['owner'], event_id, boxed_artwork())
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
            assert page.is_hidden('[data-qr-place]')
            page.select_option('#qr_corner', 'place')
            assert page.is_visible('[data-qr-place]')
            _check(page, d, 'design-qr-place', problems)

            qr = page.locator('#cdQr')
            qr.scroll_into_view_if_needed()
            page.wait_for_timeout(100)
            stage = page.locator('#cdStage').bounding_box()
            at = qr.bounding_box()
            assert abs((at['x'] - stage['x']) / stage['width'] * 100 - 82.2) < 1
            assert abs(at['width'] / stage['width'] * 100 - 11.8) < 1

            x0, y0 = float(page.input_value('#qr_x')), float(page.input_value('#qr_y'))
            page.mouse.move(at['x'] + at['width'] / 3, at['y'] + at['height'] / 3)
            page.mouse.down()
            page.mouse.move(at['x'] + at['width'] / 3 - 60, at['y'] + at['height'] / 3 + 30, steps=8)
            page.mouse.up()
            assert float(page.input_value('#qr_x')) < x0 - 2 and float(page.input_value('#qr_y')) > y0 + 2

            s0 = float(page.input_value('#qr_size'))
            handle = page.locator('#cdQr [data-handle]').bounding_box()
            page.mouse.move(handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2)
            page.mouse.down()
            page.mouse.move(handle['x'] + 40, handle['y'] + 40, steps=8)
            page.mouse.up()
            grown = float(page.input_value('#qr_size'))
            assert grown > s0 + 1
            box = qr.bounding_box()
            assert abs(box['width'] - box['height']) < 2                             # still square
            assert abs(box['width'] / stage['width'] * 100 - grown) < 0.5

            with page.expect_navigation():
                page.click('#cdForm button[type=submit]')
            assert 'Placement saved' in page.content()
            saved = design.get(_event(d, event_id))['qr']
            assert saved['corner'] == 'place' and abs(saved['size'] - grown) < 0.11
    finally:
        browser.close()
        p.stop()
    assert problems == []
