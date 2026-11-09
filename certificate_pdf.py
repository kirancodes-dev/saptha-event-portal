"""
certificate_pdf.py — draws a certificate (UPG-123).

A4 landscape, in one of two styles the organiser picks per event ("classic",
"modern"), coloured per certificate type. The college's name, logo and colours
come from settings, not the code:

    COLLEGE_NAME         (default: university_info's name)
    COLLEGE_LOGO_PATH    (a file under static/, default static/img/email-logo.png)
    CERT_PRIMARY_COLOR   (default #0c1240)
    CERT_ACCENT_COLOR    (default #c9a020)

Names in Kannada or Devanagari are drawn in Noto Sans Kannada/Devanagari and
shaped with HarfBuzz; everything else in Noto Sans. Text goes onto the canvas
as text, never as markup, so a value like "<b>" is printed as typed. A long
name shrinks to fit the page. The event's signatories (1 to 3, left to right)
sign at the bottom; the certificate number and a QR code to its verification
page on BASE_URL are in the corner.
"""
import io
import os
import re
from typing import List, Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, shapeStr
from reportlab.pdfgen import canvas as rl_canvas

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, 'static', 'fonts', 'certificate')
STYLES = ('classic', 'modern')
TYPE_ACCENTS = {'winner': '#b8860b', 'runner_up': '#7d8597', 'position': '#a0522d', 'merit': '#b8860b',
                'special_mention': '#6a4c93', 'volunteer': '#1b7f6b', 'coordinator': '#1b7f6b',
                'organiser': '#1b7f6b', 'judge': '#1b7f6b', 'speaker': '#1b7f6b'}
_FONTS = {'latin': 'CertNoto', 'kannada': 'CertNotoKannada', 'devanagari': 'CertNotoDevanagari'}
_FILES = {'latin': 'NotoSans', 'kannada': 'NotoSansKannada', 'devanagari': 'NotoSansDevanagari'}
_registered = False


def _register_fonts():
    global _registered
    if _registered:
        return
    for script, name in _FONTS.items():
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, f'{_FILES[script]}-Regular.ttf')))
        pdfmetrics.registerFont(TTFont(name + '-Bold', os.path.join(FONT_DIR, f'{_FILES[script]}-Bold.ttf')))
    _registered = True


def _script(ch: str) -> str:
    code = ord(ch)
    if 0x0C80 <= code <= 0x0CFF:
        return 'kannada'
    if 0x0900 <= code <= 0x097F or 0xA8E0 <= code <= 0xA8FF:
        return 'devanagari'
    return 'latin'


def runs(text: str):
    """Split text into (script, piece) runs; spaces and marks stay with their run."""
    out: List[list] = []
    for ch in str(text or ''):
        kind = _script(ch) if (ch.isalpha() or ord(ch) > 0x08FF) else (out[-1][0] if out else 'latin')
        if out and out[-1][0] == kind:
            out[-1][1] += ch
        else:
            out.append([kind, ch])
    return [(k, s) for k, s in out]


def _font(script: str, bold: bool) -> str:
    return _FONTS[script] + ('-Bold' if bold else '')


def _piece(script: str, piece: str, font: str, size: float):
    """What to draw for one run: Indic text shaped (joined conjuncts, placed vowel signs)."""
    return shapeStr(piece, font, size) if script != 'latin' else piece


def text_width(text: str, size: float, bold: bool = False) -> float:
    """The drawn width, measured after shaping (shaped Indic text is narrower)."""
    _register_fonts()
    total = 0.0
    for script, piece in runs(text):
        font = _font(script, bold)
        total += pdfmetrics.stringWidth(_piece(script, piece, font, size), font, size)
    return total


def draw_text(c, x: float, y: float, text: str, size: float, bold: bool = False, align: str = 'center',
              color=None):
    """Draw text in the right font for each script, shaped where needed."""
    _register_fonts()
    width = text_width(text, size, bold)
    if align == 'center':
        x -= width / 2
    elif align == 'right':
        x -= width
    if color is not None:
        c.setFillColor(color)
    for script, piece in runs(text):
        font = _font(script, bold)
        drawn = _piece(script, piece, font, size)
        c.setFont(font, size)
        c.drawString(x, y, drawn)
        x += pdfmetrics.stringWidth(drawn, font, size)


def fit_size(text: str, max_width: float, size: float, minimum: float = 12, bold: bool = True) -> float:
    """The largest size up to `size` at which text fits max_width."""
    while size > minimum and text_width(text, size, bold) > max_width:
        size -= 1
    return size


def name_lines(name: str, max_width: float, size: float = 34) -> tuple:
    """(size, lines) for the recipient's name: one line down to 22 pt, else two
    lines, smaller as needed, so even a very long name stays inside the page."""
    one = fit_size(name, max_width, size, minimum=22)
    if text_width(name, one, True) <= max_width:
        return one, [name]
    two = 22
    while two > 9:
        lines = _wrap(name, max_width, two, bold=True)
        if len(lines) <= 2 and all(text_width(line, two, True) <= max_width for line in lines):
            return two, lines
        two -= 1
    return fit_size(name, max_width, 22, minimum=6), [name]


def _wrap(text: str, max_width: float, size: float, bold: bool = False) -> List[str]:
    words, lines, line = str(text or '').split(), [], ''
    for word in words:
        trial = f'{line} {word}'.strip()
        if line and text_width(trial, size, bold) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or ['']


def branding() -> dict:
    """The college's name, logo and colours, from settings."""
    try:
        from university_info import UNIVERSITY
        default_name = UNIVERSITY['name']
    except Exception:
        default_name = 'University'
    logo = os.environ.get('COLLEGE_LOGO_PATH') or 'static/img/email-logo.png'
    logo_path = os.path.normpath(os.path.join(ROOT, logo))
    if not logo_path.startswith(os.path.join(ROOT, 'static')) or not os.path.isfile(logo_path):
        logo_path = ''
    return {'name': os.environ.get('COLLEGE_NAME') or default_name, 'logo': logo_path,
            'primary': os.environ.get('CERT_PRIMARY_COLOR') or '#0c1240',
            'accent': os.environ.get('CERT_ACCENT_COLOR') or '#c9a020'}


def _color(value: str, fallback: str):
    return HexColor(value if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value or '')) else fallback)


def _qr(url: str) -> ImageReader:
    import qrcode
    img = qrcode.make(url, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ImageReader(buf)


def _date_line(data: dict) -> str:
    start, end = str(data.get('date') or ''), str(data.get('end_date') or '')
    return f'{start} to {end}' if end and end != start else start


def render(*, number: str, name: str, data: dict, cert_type: str, signatories: List[dict],
           verify_url: str, issued_on: str, style: str = 'classic',
           signature_bytes: Optional[dict] = None) -> bytes:
    """The certificate as PDF bytes. `data` is the record's wording (services_certificates.wording);
    `signature_bytes` maps a signatory id to its trimmed PNG."""
    _register_fonts()
    brand = branding()
    primary = _color(brand['primary'], '#0c1240')
    accent = _color(TYPE_ACCENTS.get(cert_type) or brand['accent'], '#c9a020')
    style = style if style in STYLES else 'classic'
    W, H = landscape(A4)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"{data.get('title', 'Certificate')} — {name}")
    c.setAuthor(brand['name'])
    c.setSubject(f'Certificate {number}')

    # Frame
    c.setFillColor(HexColor('#fffdf7'))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    if style == 'classic':
        c.setStrokeColor(primary); c.setLineWidth(3); c.rect(20, 20, W - 40, H - 40)  # noqa: E702
        c.setStrokeColor(accent); c.setLineWidth(1.2); c.rect(30, 30, W - 60, H - 60)  # noqa: E702
    else:
        c.setFillColor(primary); c.rect(0, H - 18, W, 18, fill=1, stroke=0)  # noqa: E702
        c.setFillColor(accent); c.rect(0, 0, W, 10, fill=1, stroke=0)  # noqa: E702
        c.rect(0, 0, 14, H, fill=1, stroke=0)

    # Head: logo and college
    top = H - 62
    if brand['logo']:
        # The college's logo is light lettering made for dark backgrounds: give it a panel in its colour
        c.setFillColor(primary)
        c.roundRect(W / 2 - 125, top - 58, 250, 70, 8, fill=1, stroke=0)
        try:
            c.drawImage(ImageReader(brand['logo']), W / 2 - 115, top - 52, width=230, height=58,
                        preserveAspectRatio=True, mask='auto', anchor='c')
        except Exception:
            pass
    draw_text(c, W / 2, top - 74, brand['name'].upper(), 15, bold=True, color=primary)
    if data.get('department'):
        draw_text(c, W / 2, top - 92, data['department'], 10, color=HexColor('#55607a'))

    # Title and recipient
    draw_text(c, W / 2, H - 205, data.get('title') or 'Certificate', 30, bold=True, color=accent)
    draw_text(c, W / 2, H - 238, 'This is to certify that', 13, color=HexColor('#333a4d'))
    size, lines = name_lines(name, W - 180)
    drop = 0 if len(lines) == 1 else size + 4
    for i, line in enumerate(lines):
        draw_text(c, W / 2, H - 282 + (drop / 2 if i == 0 and drop else 0) - (drop / 2 if i else 0),
                  line, size, bold=True, color=primary)
    c.setStrokeColor(accent); c.setLineWidth(0.8)  # noqa: E702
    c.line(W / 2 - 220, H - 292 - drop / 2, W / 2 + 220, H - 292 - drop / 2)

    y = H - 314 - drop / 2
    who = ', '.join(p for p in (data.get('designation'), data.get('institution')) if p)
    if who:
        draw_text(c, W / 2, y, who, fit_size(who, W - 200, 12, bold=False), color=HexColor('#333a4d'))
        y -= 20
    sentence = f"{data.get('phrase') or 'for participating in'} {data.get('event_title') or ''}"
    if data.get('team'):
        sentence += f" as a member of {data['team']}"
    when = _date_line(data)
    if when:
        sentence += f", held on {when}"
    if data.get('hours'):
        sentence += f", {float(data['hours']):g} hours"
    if data.get('points'):
        sentence += f" ({float(data['points']):g} activity points)"
    for line in _wrap(sentence + '.', W - 200, 13)[:3]:
        draw_text(c, W / 2, y, line, 13, color=HexColor('#333a4d'))
        y -= 19

    # Signatories, left to right
    ordered = sorted(signatories or [], key=lambda s: s.get('order', 0))[:3]
    if ordered:
        slot = (W - 300) / len(ordered)
        for i, sig in enumerate(ordered):
            cx = 150 + slot * i + slot / 2
            image = (signature_bytes or {}).get(sig.get('id'))
            if image:
                try:
                    c.drawImage(ImageReader(io.BytesIO(image)), cx - 75, 146, width=150, height=48,
                                preserveAspectRatio=True, mask='auto', anchor='c')
                except Exception:
                    pass
            c.setStrokeColor(primary); c.setLineWidth(0.6)  # noqa: E702
            c.line(cx - 85, 142, cx + 85, 142)
            draw_text(c, cx, 128, sig.get('name') or '', fit_size(sig.get('name') or '', min(slot - 20, 200), 11),
                      bold=True, color=primary)
            draw_text(c, cx, 114, sig.get('title') or '',
                      fit_size(sig.get('title') or '', min(slot - 20, 210), 9, bold=False), color=HexColor('#55607a'))

    # Number, date and QR code
    c.drawImage(_qr(verify_url), W - 112, 42, width=66, height=66)
    grey = HexColor('#55607a')
    draw_text(c, 52, 70, f'Certificate No. {number}', 9, bold=True, align='left', color=grey)
    draw_text(c, 52, 57, f'Issued on {issued_on}', 8.5, align='left', color=grey)
    draw_text(c, 52, 45, f'Verify at {verify_url}', fit_size(f'Verify at {verify_url}', W - 230, 8, bold=False),
              align='left', color=grey)
    c.showPage()
    c.save()
    return buf.getvalue()


def fit_box(text: str, max_width: float, size: float, bold: bool) -> tuple:
    """(size, lines) for text in a box: one line down to 60% of the set size,
    then two lines, then smaller, so it never leaves the box's width."""
    floor = max(6.0, size * 0.6)
    one = fit_size(text, max_width, size, minimum=floor, bold=bold)
    if text_width(text, one, bold) <= max_width:
        return one, [text]
    two = one
    while two >= 6:
        lines = _wrap(text, max_width, two, bold=bold)
        if len(lines) <= 2 and all(text_width(line, two, bold) <= max_width for line in lines):
            return two, lines
        two -= 1
    return fit_size(text, max_width, floor, minimum=3, bold=bold), [text]


QR_SIZE = 62          # about 22 mm
QR_MARGIN = 24        # about 8.5 mm from the page's edges


def qr_box(corner: str, W: float, H: float) -> tuple:
    """(x, y) of the QR code's bottom-left corner, in points from the page's bottom left."""
    left = corner in ('bl', 'tl')
    top = corner in ('tr', 'tl')
    x = QR_MARGIN if left else W - QR_MARGIN - QR_SIZE
    y = H - QR_MARGIN - QR_SIZE if top else QR_MARGIN + 10      # room for the number under it
    return x, y


def render_design(*, number: str, name: str, data: dict, design: dict, image: bytes, verify_url: str) -> bytes:
    """A certificate on the organiser's own design (UPG-206): the design full
    page, the name (and any other boxes switched on) where the organiser
    placed them, and the number with a small QR code in the chosen corner."""
    from services_certificate_design import FIELDS, values
    _register_fonts()
    W, H = landscape(A4) if design.get('orientation') != 'portrait' else A4
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"{data.get('title', 'Certificate')} — {name}")
    c.setAuthor(branding()['name'])
    c.setSubject(f'Certificate {number}')
    c.drawImage(ImageReader(io.BytesIO(image)), 0, 0, width=W, height=H)

    texts = values(name, data)
    for key in FIELDS:
        box = (design.get('fields') or {}).get(key) or {}
        text = str(texts.get(key) or '').strip()
        if not box.get('on') or not text:
            continue
        width = W * float(box['w']) / 100
        left = W * float(box['x']) / 100
        middle = H - H * float(box['y']) / 100            # the box's centre line
        bold = bool(box.get('bold'))
        size, lines = fit_box(text, width, float(box['size']), bold)
        gap = size * 1.15
        align = box.get('align') if box.get('align') in ('left', 'center', 'right') else 'center'
        x = left if align == 'left' else left + width if align == 'right' else left + width / 2
        first = middle + gap * (len(lines) - 1) / 2 - size * 0.35
        for i, line in enumerate(lines):
            draw_text(c, x, first - gap * i, line, size, bold=bold, align=align,
                      color=_color(str(box.get('color') or ''), '#1a1a1a'))

    qx, qy = qr_box((design.get('qr') or {}).get('corner') or 'br', W, H)
    label = f'No. {number}'
    size = fit_size(label, QR_SIZE + 2 * QR_MARGIN - 8, 7, minimum=5, bold=False)
    half = max(QR_SIZE, text_width(label, size)) / 2 + 3
    c.setFillColor(HexColor('#ffffff'))
    c.rect(qx + QR_SIZE / 2 - half, qy - 12, 2 * half, QR_SIZE + 15, fill=1, stroke=0)
    c.drawImage(_qr(verify_url), qx, qy, width=QR_SIZE, height=QR_SIZE)
    draw_text(c, qx + QR_SIZE / 2, qy - 9, label, size, color=HexColor('#333a4d'))
    c.showPage()
    c.save()
    return buf.getvalue()


def to_png(pdf: bytes, scale: float = 2.0) -> bytes:
    """The certificate's first page as a PNG (for previews and LinkedIn)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    try:
        image = doc[0].render(scale=scale).to_pil()
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        return buf.getvalue()
    finally:
        doc.close()


def text_of(pdf: bytes) -> str:
    """The PDF's text (tests check what a certificate says)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    try:
        return '\n'.join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    finally:
        doc.close()
