"""
tests/test_certificate_fonts.py — UPG-330 on the real database layer: a font
for each box of the organiser's own certificate design. The ready fonts and
the organiser's own uploaded TrueType font; bad, PostScript, oversized and
repeated files are refused; only editors upload and only organisers fetch
the file; a letter the font lacks prints in Noto Sans and Kannada keeps its
own font; issued certificates keep their font after it is changed or
removed; and the placement page lists the fonts and loads them.
"""
import io
import os
import re
import struct

import certificate_pdf
import services_certificate_design as design
import services_certificates as certs
from tests.test_certificate_design import _cert, _event, _issue, _settings, _upload, artwork, site  # noqa: F401

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'fonts', 'certificate')


def _font(name):
    with open(os.path.join(FONT_DIR, name), 'rb') as fh:
        return fh.read()


def _send_font(client, event_id, data, filename='MyFont.ttf'):
    return client.post(f'/certificates/events/{event_id}/design/fonts', data={'font': (io.BytesIO(data), filename)},
                       content_type='multipart/form-data', follow_redirects=True)


def _pdf_fonts(pdf):
    """The PostScript names of the fonts embedded in the PDF, without the subset prefix."""
    return {n.split(b'+', 1)[-1].decode() for n in re.findall(rb'/BaseFont /([^\s/]+)', pdf)}


def _designed(d, **people):
    event_id = d['event']()
    assert _upload(d['clients']['owner'], event_id, artwork()).status_code == 200
    emails = {name: d['person'](event_id, name) for name in people.get('names', ['Asha Rao'])}
    return event_id, emails


# ── Criterion 1: the ready fonts ────────────────────────────────────────────

def test_each_ready_font_is_listed_stored_and_printed(site):  # noqa: F811
    d = site
    keys = [c['key'] for c in design.font_choices(None)]
    assert keys[0] == 'noto' and {'poppins', 'montserrat', 'playfair', 'cinzel', 'tinos', 'greatvibes',
                                  'dancing'} <= set(keys)
    for key, (_label, regular, bold) in certificate_pdf.FACES.items():
        assert os.path.exists(os.path.join(FONT_DIR, regular)), key
        assert bold is None or os.path.exists(os.path.join(FONT_DIR, bold)), key

    event_id, emails = _designed(d)
    page = _settings(d['clients']['owner'], event_id, name_font='playfair', name_bold='')
    assert page.status_code == 200
    assert design.get(_event(d, event_id))['fields']['name']['font'] == 'playfair'
    # a font the list doesn't have keeps the box's font
    _settings(d['clients']['owner'], event_id, name_font='comic-sans', name_bold='')
    assert design.get(_event(d, event_id))['fields']['name']['font'] == 'playfair'

    _issue(d, event_id)
    pdf = certs.render(_event(d, event_id), _cert(event_id, emails['Asha Rao']))
    assert any(f.startswith('PlayfairDisplay') and f.endswith('-Regular') for f in _pdf_fonts(pdf))

    # Bold uses the font's bold file
    _settings(d['clients']['owner'], event_id, name_font='cinzel', name_bold='1')
    pdf = certificate_pdf.render_design(number='SE-1', name='Asha Rao', data={}, design=design.get(_event(d, event_id)),
                                        image=artwork(), verify_url='https://x/v/SE-1')
    assert any(f.startswith('Cinzel') and f.endswith('-Bold') for f in _pdf_fonts(pdf))


def test_a_design_without_fonts_prints_in_noto_as_before(site):  # noqa: F811
    d = site
    event_id, emails = _designed(d)
    current = design.get(_event(d, event_id))
    old = dict(current, fields={k: {f: v for f, v in box.items() if f != 'font'} for k, box in current['fields'].items()})
    old.pop('fonts')
    d['db'].collection('events').document(event_id).update({design.FIELD: old})
    got = design.get(_event(d, event_id))
    assert got['fields']['name']['font'] == 'noto' and got['fonts'] == []
    pdf = certificate_pdf.render_design(number='SE-1', name='Asha Rao', data={}, design=got, image=artwork(),
                                        verify_url='https://x/v/SE-1')
    assert {f for f in _pdf_fonts(pdf) if f != 'Helvetica'} <= {'NotoSans-Regular', 'NotoSans-Bold'}


# ── Criterion 2: the organiser's own font ───────────────────────────────────

def test_an_uploaded_ttf_is_named_used_and_served_only_to_organisers(site):  # noqa: F811
    d = site
    event_id, emails = _designed(d)
    owner = d['clients']['owner']
    for who in ('other', 'student'):
        assert _send_font(d['clients'][who], event_id, _font('Tinos-Regular.ttf')).status_code == 403, who

    page = _send_font(owner, event_id, _font('Tinos-Regular.ttf'), 'TTRamillas-Regular.ttf')
    assert 'Tinos is uploaded' in page.get_data(as_text=True)
    fonts = design.get(_event(d, event_id))['fonts']
    assert [f['name'] for f in fonts] == ['Tinos'] and fonts[0]['filename'] == 'TTRamillas-Regular.ttf'
    font_id = fonts[0]['id']

    url = f'/certificates/events/{event_id}/design/fonts/{font_id}.ttf'
    got = owner.get(url)
    assert got.status_code == 200 and got.mimetype == 'font/ttf' and got.data == _font('Tinos-Regular.ttf')
    assert 'no-store' in got.headers['Cache-Control'] and 'private' in got.headers['Cache-Control']
    for who in ('other', 'student'):
        assert d['clients'][who].get(url).status_code == 403, who
    assert owner.get(f'/certificates/events/{event_id}/design/fonts/up-nothere.ttf').status_code == 404

    _settings(owner, event_id, name_font=font_id, name_bold='')
    assert design.get(_event(d, event_id))['fields']['name']['font'] == font_id
    _issue(d, event_id)
    pdf = certs.render(_event(d, event_id), _cert(event_id, emails['Asha Rao']))
    assert 'Tinos-Regular' in _pdf_fonts(pdf)


def test_bad_postscript_large_and_repeated_font_files_are_refused(site):  # noqa: F811
    d = site
    event_id, _ = _designed(d)
    owner = d['clients']['owner']
    otf = b'OTTO' + struct.pack('>HHHH', 1, 16, 0, 0) + b'CFF ' + b'\0' * 12
    cases = [(otf, "Upload the .ttf version"), (b'not a font' * 50, "a font file the certificate can use"),
             (b'\0' * (design.FONT_MAX_BYTES + 1), "5 MB or smaller")]
    for data, says in cases:
        assert says in _send_font(owner, event_id, data).get_data(as_text=True), says
    assert design.get(_event(d, event_id))['fonts'] == []

    _send_font(owner, event_id, _font('Cinzel-Regular.ttf'))
    assert 'already uploaded' in _send_font(owner, event_id, _font('Cinzel-Regular.ttf'), 'again.ttf').get_data(as_text=True)
    assert len(design.get(_event(d, event_id))['fonts']) == 1

    # no design yet: nothing to add a font to
    bare = d['event']()
    assert 'Upload a design first' in _send_font(owner, bare, _font('Cinzel-Regular.ttf')).get_data(as_text=True)


def test_an_event_holds_at_most_max_fonts(site, monkeypatch):  # noqa: F811
    d = site
    event_id, _ = _designed(d)
    monkeypatch.setattr(design, 'MAX_FONTS', 2)
    for name in ('Cinzel-Regular.ttf', 'Tinos-Regular.ttf'):
        _send_font(d['clients']['owner'], event_id, _font(name))
    page = _send_font(d['clients']['owner'], event_id, _font('Poppins-Regular.ttf')).get_data(as_text=True)
    assert 'at most 2 fonts' in page
    assert len(design.get(_event(d, event_id))['fonts']) == 2


# ── Criterion 3: letters the font lacks, and Kannada ────────────────────────

def test_a_letter_the_font_lacks_prints_in_noto_and_kannada_keeps_its_font():
    face = certificate_pdf.builtin_face('greatvibes')
    noto = certificate_pdf._FONTS['latin']
    missing = next(ch for ch in '→☆ŉǅ₹' if not face.has(ch) and ord(ch) in __import__(
        'reportlab.pdfbase.pdfmetrics', fromlist=['x']).getFont(noto).face.charToGlyph)
    pieces = certificate_pdf.runs(f'Asha {missing} ಕಿರಣ್', face)
    scripts = [script for script, _text in pieces]
    assert scripts[0] == 'face' and 'latin' in scripts and 'kannada' in scripts
    assert next(t for s, t in pieces if s == 'latin').strip() == missing

    box = {'on': True, 'x': 10, 'y': 45, 'w': 80, 'size': 40, 'color': '#112233', 'align': 'center', 'bold': True,
           'font': 'greatvibes'}
    plan = {'fields': dict(design.DEFAULT_FIELDS, name=box), 'qr': {'corner': 'br'}, 'fonts': [],
            'width': 3508, 'height': 2480, 'kind': 'image', 'key': 'x'}
    plan = design.get({design.FIELD: plan}) or plan
    pdf = certificate_pdf.render_design(number='SE-1', name=f'Asha {missing} ಕಿರಣ್', data={}, design=plan,
                                        image=artwork(), verify_url='https://x/v/SE-1')
    fonts = _pdf_fonts(pdf)
    # Great Vibes has no bold file, so Bold prints its regular
    assert 'GreatVibes-Regular' in fonts and any(f.startswith('NotoSans-') for f in fonts)
    assert any('Kannada' in f for f in fonts)


# ── Criterion 4: issued certificates keep their font ────────────────────────

def test_issued_certificates_keep_their_font_after_a_change_or_removal(site):  # noqa: F811
    d = site
    event_id, emails = _designed(d)
    owner = d['clients']['owner']
    _send_font(owner, event_id, _font('Tinos-Regular.ttf'))
    font_id = design.get(_event(d, event_id))['fonts'][0]['id']
    _settings(owner, event_id, name_font=font_id, name_bold='')
    _issue(d, event_id)
    cert = _cert(event_id, emails['Asha Rao'])
    assert cert['data']['design']['fields']['name']['font'] == font_id

    page = owner.post(f'/certificates/events/{event_id}/design/fonts/{font_id}/delete', follow_redirects=True)
    assert 'is removed' in page.get_data(as_text=True)
    now = design.get(_event(d, event_id))
    assert now['fonts'] == [] and now['fields']['name']['font'] == 'noto'
    assert d['clients']['student'].post(f'/certificates/events/{event_id}/design/fonts/{font_id}/delete').status_code == 403

    certificate_pdf._faces.clear()      # a new process: the font comes from storage again
    pdf = certs.render(_event(d, event_id), cert)
    assert 'Tinos-Regular' in _pdf_fonts(pdf)

    _settings(owner, event_id, name_font='poppins', name_bold='')
    assert 'Tinos-Regular' in _pdf_fonts(certs.render(_event(d, event_id), cert))


# ── Criterion 5: the placement page ─────────────────────────────────────────

def test_the_page_lists_the_fonts_with_their_files_for_the_preview(site):  # noqa: F811
    d = site
    event_id, _ = _designed(d)
    owner = d['clients']['owner']
    _send_font(owner, event_id, _font('Tinos-Regular.ttf'))
    font_id = design.get(_event(d, event_id))['fonts'][0]['id']
    _settings(owner, event_id, name_font='dancing', name_bold='')
    html = owner.get(f'/certificates/events/{event_id}').get_data(as_text=True)

    assert 'id="name_font"' in html and 'name="name_font"' in html
    assert re.search(r'<option value="dancing" data-family="cert-dancing" data-bold="1" [^>]*\bselected>', html)
    assert '<optgroup label="Your fonts">' in html
    assert f'<option value="{font_id}" data-family="cert-{font_id}" data-bold="0"' in html
    assert 'value="greatvibes" data-family="cert-greatvibes" data-bold="0"' in html
    assert ('data-url="/static/fonts/certificate/Poppins-Regular.ttf" '
            'data-bold-url="/static/fonts/certificate/Poppins-Bold.ttf"') in html
    assert f'data-url="/certificates/events/{event_id}/design/fonts/{font_id}.ttf" data-bold-url=""' in html
    assert '@font-face' not in html          # the site's own fonts stay the three families (UPG-24)
    assert 'Upload font' in html and f'/design/fonts/{font_id}/delete' in html
    for name in ('Poppins-Regular.ttf', 'GreatVibes-Regular.ttf'):
        assert owner.get(f'/static/fonts/certificate/{name}').status_code == 200


def test_choosing_a_font_changes_the_preview_box_in_the_browser(site):  # noqa: F811
    from tests.headless import chromium, live_server
    from tests.test_phone_journey import DESKTOP, _login_in_browser, _routes
    d = site
    event_id, _ = _designed(d)
    _send_font(d['clients']['owner'], event_id, _font('Tinos-Regular.ttf'))
    font_id = design.get(_event(d, event_id))['fonts'][0]['id']
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            ctx = browser.new_context(viewport=DESKTOP)
            _routes(ctx, server.url)
            page = ctx.new_page()
            _login_in_browser(page, server.url, d['people']['owner'], 'ClubSPOC')
            page.goto(f'{server.url}/certificates/events/{event_id}#design')
            page.wait_for_selector('#cdStage img')
            text = '[data-field="name"] [data-text]'

            def style(prop):
                return page.eval_on_selector(text, f'e => getComputedStyle(e).{prop}')
            page.check('#name_bold')
            page.select_option('#name_font', 'cinzel')
            assert 'cert-cinzel' in style('fontFamily') and style('fontWeight') == '700'
            # a font with no bold file shows as it prints: regular
            page.select_option('#name_font', 'greatvibes')
            assert 'cert-greatvibes' in style('fontFamily') and style('fontWeight') == '400'
            page.select_option('#name_font', font_id)
            assert f'cert-{font_id}' in style('fontFamily')
            page.select_option('#name_font', 'cinzel')
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.fonts.check(\'700 20px "cert-cinzel"\')')
            page.select_option('#name_font', font_id)
            assert page.evaluate(f'document.fonts.load(\'20px "cert-{font_id}"\').then(f => f.length)') == 1
            with page.expect_navigation():
                page.click('#cdForm button[type=submit]')
            assert design.get(_event(d, event_id))['fields']['name']['font'] == font_id
    finally:
        browser.close()
        p.stop()
