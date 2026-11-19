"""
services_certificate_design.py — the organiser's own certificate design (UPG-206).

An event can use a finished certificate design (PNG, JPG or a one-page PDF,
A4 landscape or portrait, at most 5 MB) for the certificate everyone who
attended gets: participation, or completion / service for workshops and NSS
events (services_certificates.attendance_type). Logos, borders and signatures
are already on the design, so the app writes only the person's name (and,
when switched on, the team, USN and college) in boxes the organiser places,
plus the certificate number and a small QR code to its verification page:
in a corner, or (UPG-315) in a box the organiser places, such as the design's
own "scan to verify" box, with the number then in a box of its own.

The design is normalised once on upload (flattened on white, at most 3508 px
on the long side, JPEG) and stored privately (utils_storage.put_private),
never under static/. Box positions are percentages of the page, so the same
settings work at any image size. Each certificate keeps a snapshot of the
design and its settings as issued, so a later change affects only
certificates issued afterwards. Changes are audit-logged.

Each box prints in a font the organiser picks (UPG-330): one of the free
fonts that come with the app (certificate_pdf.FACES), or a TrueType font
they upload to match their design's lettering, stored privately like the
design. A letter the font lacks prints in Noto Sans. Removing an uploaded
font keeps its file: certificates issued with it still use it.
"""
import hashlib
import io
import re
import uuid
from typing import Optional

FIELD = 'cert_design'
MAX_BYTES = 5 * 1024 * 1024
A4_RATIO = 297 / 210
RATIO_TOLERANCE = 0.02
BEST = (3508, 2480)
LOW_RES = 2000
LONG_SIDE = 3508
CORNERS = ('br', 'bl', 'tr', 'tl')
PLACE = 'place'                     # the QR where the organiser puts it (UPG-315)
QR_CHOICES = CORNERS + (PLACE,)
ALIGNS = ('left', 'center', 'right')
FIELDS = ('name', 'team', 'usn', 'college', 'number')
LABELS = {'name': 'Name', 'team': 'Team name', 'usn': 'USN', 'college': 'College / institution',
          'number': 'Certificate number'}
SAMPLES = {'team': 'Team Sample', 'usn': '1SG22CS000', 'college': 'Sample Institute of Technology',
           'number': 'SE-2026-AB12-CD34-5'}

DEFAULT_FIELDS = {
    'name':    {'on': True, 'x': 20.0, 'y': 47.0, 'w': 60.0, 'size': 40.0, 'color': '#1a1a1a', 'align': 'center', 'bold': True},
    'team':    {'on': False, 'x': 25.0, 'y': 56.0, 'w': 50.0, 'size': 18.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
    'usn':     {'on': False, 'x': 25.0, 'y': 62.0, 'w': 50.0, 'size': 14.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
    'college': {'on': False, 'x': 20.0, 'y': 67.0, 'w': 60.0, 'size': 16.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
    'number':  {'on': False, 'x': 70.0, 'y': 92.0, 'w': 25.0, 'size': 8.0, 'color': '#333a4d', 'align': 'center', 'bold': False},
}
# x and y: the QR's top-left corner, % of the page's width and height; size: its side, % of the page's width
DEFAULT_QR = {'corner': 'br', 'x': 82.2, 'y': 44.8, 'size': 11.8}
QR_MIN, QR_MAX = 5.0, 30.0
FONT_MAX_BYTES = 5 * 1024 * 1024
MAX_FONTS = 10


class DesignError(ValueError):
    pass


class FontError(DesignError):
    pass


def _default_face() -> str:
    from certificate_pdf import DEFAULT_FACE
    return DEFAULT_FACE


def font_choices(design: Optional[dict], event_id: str = '') -> list:
    """Each font a box can use (UPG-330): the ready ones, then the organiser's
    own, with the CSS family and file URLs the placement preview loads."""
    from certificate_pdf import FACES
    base = '/static/fonts/certificate/'
    out = [{'key': key, 'label': label, 'own': False, 'family': f'cert-{key}', 'url': base + regular,
            'bold_url': base + bold if bold else ''} for key, (label, regular, bold) in FACES.items()]
    return out + [{'key': f['id'], 'label': f['name'], 'own': True, 'family': f"cert-{f['id']}",
                   'url': f"/certificates/events/{event_id}/design/fonts/{f['id']}.ttf", 'bold_url': ''}
                  for f in (design or {}).get('fonts') or []]


def _font_keys(design: Optional[dict]) -> set:
    return {c['key'] for c in font_choices(design)}


# ── The upload ──────────────────────────────────────────────────────────────

def _shape_message(w: int, h: int) -> str:
    return (f"The design must be A4 shape, landscape or portrait (297 × 210 mm). This file is {w} × {h} px; "
            f"the best size is {BEST[0]} × {BEST[1]} px (A4 at 300 dpi).")


def _from_pdf(data: bytes):
    import pypdfium2 as pdfium
    try:
        doc = pdfium.PdfDocument(data)
    except Exception:
        raise DesignError("That PDF couldn't be opened. Upload a PNG, JPG or a one-page PDF.")
    try:
        if len(doc) != 1:
            raise DesignError("Upload a one-page PDF (this one has %d pages)." % len(doc))
        page = doc[0]
        w, h = page.get_size()
        scale = LONG_SIDE / max(w, h)
        return page.render(scale=scale).to_pil()
    finally:
        doc.close()


def process(data: bytes) -> dict:
    """The upload as a normalised JPEG with its size and orientation, or
    DesignError saying what's wrong with it."""
    from PIL import Image, UnidentifiedImageError
    if not data:
        raise DesignError("Choose a design file to upload.")
    if len(data) > MAX_BYTES:
        raise DesignError("The design must be 5 MB or smaller.")
    if data[:5] == b'%PDF-':
        image = _from_pdf(data)
    else:
        try:
            image = Image.open(io.BytesIO(data))
            kind = image.format
            image.load()
        except (UnidentifiedImageError, OSError):
            raise DesignError("Upload the design as a PNG, JPG or one-page PDF.")
        if kind not in ('PNG', 'JPEG'):
            raise DesignError("Upload the design as a PNG, JPG or one-page PDF.")
    w, h = image.size
    if not w or not h or abs(max(w, h) / min(w, h) - A4_RATIO) > A4_RATIO * RATIO_TOLERANCE:
        raise DesignError(_shape_message(w, h))
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGBA')
        flat = Image.new('RGB', image.size, (255, 255, 255))
        flat.paste(image, mask=image.split()[-1])
        image = flat
    else:
        image = image.convert('RGB')
    if max(w, h) > LONG_SIDE:
        image.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=88, optimize=True)
    return {'jpeg': buf.getvalue(), 'width': w, 'height': h,
            'orientation': 'landscape' if w >= h else 'portrait', 'low_res': max(w, h) < LOW_RES}


# ── Settings ────────────────────────────────────────────────────────────────

def get(event: dict) -> Optional[dict]:
    """The event's design with complete settings, or None."""
    design = (event or {}).get(FIELD)
    if not isinstance(design, dict) or not design.get('image_key'):
        return None
    fields = {}
    for key in FIELDS:
        saved = (design.get('fields') or {}).get(key)
        fields[key] = dict(DEFAULT_FIELDS[key], **(saved if isinstance(saved, dict) else {}))
    fields['name']['on'] = True
    fonts = [f for f in design.get('fonts') or [] if isinstance(f, dict) and f.get('id') and f.get('key')]
    known = _font_keys({'fonts': fonts})
    for box in fields.values():
        box['font'] = box.get('font') if box.get('font') in known else _default_face()
    qr = dict(DEFAULT_QR, **(design.get('qr') if isinstance(design.get('qr'), dict) else {}))
    if qr['corner'] not in QR_CHOICES:
        qr['corner'] = DEFAULT_QR['corner']
    return dict(design, fields=fields, qr=qr, fonts=fonts)


def page_ratio(design: dict) -> float:
    """The page's height over its width (A4, as the PDF is drawn)."""
    return 297 / 210 if design.get('orientation') == 'portrait' else 210 / 297


def parse_qr(form, current: dict, ratio: float) -> dict:
    """The QR's corner, or its box when placed (UPG-315), clamped so it stays on the page."""
    current = dict(DEFAULT_QR, **(current or {}))
    corner = str(form.get('qr_corner') or current['corner'])
    corner = corner if corner in QR_CHOICES else current['corner']
    size = _number(form.get('qr_size'), float(current['size']), QR_MIN, QR_MAX)
    x = _number(form.get('qr_x'), float(current['x']), 0, 100)
    y = _number(form.get('qr_y'), float(current['y']), 0, 100)
    tall = size / ratio                     # the square's height, % of the page's height
    return {'corner': corner, 'size': size, 'x': min(x, round(100 - size, 2)), 'y': min(y, round(100 - tall, 2))}


def covers(event: dict, cert_type: str) -> bool:
    """Is this type drawn on the event's own design? The certificate everyone who attended gets."""
    from services_certificates import attendance_type
    return get(event) is not None and cert_type == attendance_type(event)


def _number(value, default: float, low: float, high: float) -> float:
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if n != n:          # NaN
        return default
    return round(min(max(n, low), high), 2)


def parse_fields(form, current: Optional[dict] = None, fonts: Optional[list] = None) -> dict:
    """Box settings from a submitted form (`<field>_x`, `_y`, `_w`, `_size`,
    `_color`, `_align`, `_bold`, `_on`, `_font`), each clamped to a sensible
    range; a font must be a ready one or one of `fonts` (UPG-330)."""
    current = current or {}
    known = _font_keys({'fonts': fonts or []})
    out = {}
    for key in FIELDS:
        base = dict(DEFAULT_FIELDS[key], **(current.get(key) or {}))
        font = str(form.get(f'{key}_font') or base.get('font') or _default_face())
        w = _number(form.get(f'{key}_w'), base['w'], 5, 100)
        x = _number(form.get(f'{key}_x'), base['x'], 0, 95)
        x = min(x, round(100 - w, 2))
        color = str(form.get(f'{key}_color') or base['color']).strip()
        align = str(form.get(f'{key}_align') or base['align'])
        out[key] = {'on': True if key == 'name' else form.get(f'{key}_on') in ('1', 'on', 'true'),
                    'x': x, 'y': _number(form.get(f'{key}_y'), base['y'], 2, 98), 'w': w,
                    'size': _number(form.get(f'{key}_size'), base['size'], 6, 120),
                    'color': color if re.fullmatch(r'#[0-9a-fA-F]{6}', color) else base['color'],
                    'align': align if align in ALIGNS else base['align'],
                    'bold': form.get(f'{key}_bold') in ('1', 'on', 'true'),
                    'font': font if font in known else (base.get('font') if base.get('font') in known
                                                        else _default_face())}
    return out


def _audit(db, actor: str, action: str, details: str) -> None:
    from utils import log_action
    log_action(db, action, f"{actor}: {details}")


def upload(db, event_id: str, data: bytes, filename: str = '', actor: str = '') -> dict:
    """Store a new design for the event; the box settings of an earlier design are kept."""
    import datetime
    from utils_storage import put_private
    processed = process(data)
    doc = db.collection('events').document(event_id).get()
    old = get(doc.to_dict() or {}) if doc.exists else None
    key = put_private(processed['jpeg'], f"cert_designs/{event_id}/{uuid.uuid4().hex}.jpg", 'image/jpeg')
    design = {'image_key': key, 'sha256': hashlib.sha256(processed['jpeg']).hexdigest(),
              'orientation': processed['orientation'], 'width': processed['width'], 'height': processed['height'],
              'low_res': processed['low_res'], 'filename': str(filename or '')[:200],
              'uploaded_by': actor, 'uploaded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'fields': (old or {}).get('fields') or {k: dict(v) for k, v in DEFAULT_FIELDS.items()},
              'qr': (old or {}).get('qr') or dict(DEFAULT_QR), 'fonts': (old or {}).get('fonts') or []}
    db.collection('events').document(event_id).update({FIELD: design})
    _audit(db, actor, "CERT_DESIGN_UPLOADED",
           f"{design['width']}x{design['height']} {design['orientation']} design for event {event_id}"
           + (" (replacing the earlier one)" if old else ""))
    return design


def save_settings(db, event_id: str, event: dict, form, actor: str = '') -> dict:
    design = get(event)
    if design is None:
        raise DesignError("Upload a design first.")
    design = dict(design, fields=parse_fields(form, design['fields'], design['fonts']),
                  qr=parse_qr(form, design['qr'], page_ratio(design)))
    db.collection('events').document(event_id).update({FIELD: design})
    name = design['fields']['name']
    _audit(db, actor, "CERT_DESIGN_CHANGED",
           f"event {event_id}: name at {name['y']}% from the top, {name['x']}% from the left, "
           f"{name['w']}% wide, {name['size']} pt, font {name['font']}; QR {_qr_text(design['qr'])}")
    return design


# ── The organiser's own fonts (UPG-330) ─────────────────────────────────────

def _decode(value) -> str:
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'replace')
    return re.sub(r'[\x00-\x1f]', '', str(value or '')).strip()


def check_font(data: bytes) -> str:
    """The font's name ("Family Style") if the PDF can embed it, else FontError saying why."""
    import certificate_pdf
    if not data:
        raise FontError("Choose a font file (.ttf) to upload.")
    if len(data) > FONT_MAX_BYTES:
        raise FontError("The font file must be 5 MB or smaller.")
    try:
        font = certificate_pdf.load_font(data, f"CertCheck-{hashlib.sha256(data).hexdigest()[:16]}")
    except Exception as exc:
        if 'postscript' in str(exc).lower():
            raise FontError("This font has PostScript outlines (an .otf the PDF can't embed). "
                            "Upload the .ttf version of the same font.")
        raise FontError("That isn't a font file the certificate can use. Upload a TrueType font (.ttf).")
    family, style = _decode(font.face.familyName), _decode(font.face.styleName)
    if not all(ord(ch) in font.face.charToGlyph for ch in 'AZaz'):
        raise FontError("This font has no English letters, so it can't print names.")
    name = f"{family} {style}".strip() if style and style.lower() not in ('regular', 'book') else family
    return (name or 'Uploaded font')[:80]


def upload_font(db, event_id: str, event: dict, data: bytes, filename: str = '', actor: str = '') -> dict:
    """Add a font the boxes can use; the same file twice is refused."""
    import datetime
    from utils_storage import put_private
    design = get(event)
    if design is None:
        raise FontError("Upload a design first.")
    if len(design['fonts']) >= MAX_FONTS:
        raise FontError(f"An event can have at most {MAX_FONTS} fonts. Remove one first.")
    name = check_font(data)
    digest = hashlib.sha256(data).hexdigest()
    if any(f.get('sha256') == digest for f in design['fonts']):
        raise FontError(f"{name} is already uploaded.")
    token = uuid.uuid4().hex
    key = put_private(data, f"cert_fonts/{event_id}/{token}.ttf", 'font/ttf')
    entry = {'id': f'up-{token[:12]}', 'name': name, 'key': key, 'sha256': digest,
             'filename': str(filename or '')[:200], 'uploaded_by': actor,
             'uploaded_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    design = dict(design, fonts=design['fonts'] + [entry])
    db.collection('events').document(event_id).update({FIELD: design})
    _audit(db, actor, "CERT_FONT_UPLOADED", f"{name} for event {event_id}")
    return entry


def remove_font(db, event_id: str, event: dict, font_id: str, actor: str = '') -> Optional[dict]:
    """Take a font off the list; boxes using it go back to the default. The
    file stays stored: certificates issued with it still print in it."""
    design = get(event)
    if design is None:
        return None
    entry = next((f for f in design['fonts'] if f['id'] == font_id), None)
    if entry is None:
        return None
    fields = {k: dict(v, font=_default_face()) if v.get('font') == font_id else v for k, v in design['fields'].items()}
    design = dict(design, fields=fields, fonts=[f for f in design['fonts'] if f['id'] != font_id])
    db.collection('events').document(event_id).update({FIELD: design})
    _audit(db, actor, "CERT_FONT_REMOVED", f"{entry['name']} for event {event_id}")
    return entry


def font_file(design: dict, font_id: str) -> Optional[bytes]:
    from utils_storage import get_private
    entry = next((f for f in (design or {}).get('fonts') or [] if f.get('id') == font_id), None)
    return get_private(entry['key']) if entry else None


def _qr_text(qr: dict) -> str:
    if qr['corner'] != PLACE:
        return qr['corner']
    return f"placed {qr['y']}% from the top, {qr['x']}% from the left, {qr['size']}% wide"


def remove(db, event_id: str, actor: str = '') -> None:
    """Back to the built-in templates. The file stays stored: certificates issued with it still use it."""
    db.collection('events').document(event_id).update({FIELD: None})
    _audit(db, actor, "CERT_DESIGN_REMOVED", f"event {event_id}")


def snapshot(event: dict) -> Optional[dict]:
    """What a certificate keeps of the design as issued."""
    design = get(event)
    if design is None:
        return None
    return {k: design[k] for k in ('image_key', 'sha256', 'orientation', 'fields', 'qr', 'fonts')}


def image(design: dict) -> bytes:
    from utils_storage import get_private
    return get_private(design['image_key'])


def values(name: str, data: dict, number: str = '') -> dict:
    """What goes in each box for one certificate."""
    return {'name': name, 'team': data.get('team') or '', 'usn': data.get('usn') or '',
            'college': data.get('institution') or data.get('college') or '', 'number': number}
