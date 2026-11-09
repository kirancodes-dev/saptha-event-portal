"""
services_certificate_design.py — the organiser's own certificate design (UPG-206).

An event can use a finished certificate design (PNG, JPG or a one-page PDF,
A4 landscape or portrait, at most 5 MB) for the certificate everyone who
attended gets: participation, or completion / service for workshops and NSS
events (services_certificates.attendance_type). Logos, borders and signatures
are already on the design, so the app writes only the person's name (and,
when switched on, the team, USN and college) in boxes the organiser places,
plus the certificate number and a small QR code to its verification page.

The design is normalised once on upload (flattened on white, at most 3508 px
on the long side, JPEG) and stored privately (utils_storage.put_private),
never under static/. Box positions are percentages of the page, so the same
settings work at any image size. Each certificate keeps a snapshot of the
design and its settings as issued, so a later change affects only
certificates issued afterwards. Changes are audit-logged.
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
ALIGNS = ('left', 'center', 'right')
FIELDS = ('name', 'team', 'usn', 'college')
LABELS = {'name': 'Name', 'team': 'Team name', 'usn': 'USN', 'college': 'College / institution'}
SAMPLES = {'team': 'Team Sample', 'usn': '1SG22CS000', 'college': 'Sample Institute of Technology'}

DEFAULT_FIELDS = {
    'name':    {'on': True, 'x': 20.0, 'y': 47.0, 'w': 60.0, 'size': 40.0, 'color': '#1a1a1a', 'align': 'center', 'bold': True},
    'team':    {'on': False, 'x': 25.0, 'y': 56.0, 'w': 50.0, 'size': 18.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
    'usn':     {'on': False, 'x': 25.0, 'y': 62.0, 'w': 50.0, 'size': 14.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
    'college': {'on': False, 'x': 20.0, 'y': 67.0, 'w': 60.0, 'size': 16.0, 'color': '#1a1a1a', 'align': 'center', 'bold': False},
}
DEFAULT_QR = {'corner': 'br'}


class DesignError(ValueError):
    pass


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
    qr = dict(DEFAULT_QR, **(design.get('qr') if isinstance(design.get('qr'), dict) else {}))
    return dict(design, fields=fields, qr=qr)


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


def parse_fields(form, current: Optional[dict] = None) -> dict:
    """Box settings from a submitted form (`<field>_x`, `_y`, `_w`, `_size`,
    `_color`, `_align`, `_bold`, `_on`), each clamped to a sensible range."""
    current = current or {}
    out = {}
    for key in FIELDS:
        base = dict(DEFAULT_FIELDS[key], **(current.get(key) or {}))
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
                    'bold': form.get(f'{key}_bold') in ('1', 'on', 'true')}
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
              'qr': (old or {}).get('qr') or dict(DEFAULT_QR)}
    db.collection('events').document(event_id).update({FIELD: design})
    _audit(db, actor, "CERT_DESIGN_UPLOADED",
           f"{design['width']}x{design['height']} {design['orientation']} design for event {event_id}"
           + (" (replacing the earlier one)" if old else ""))
    return design


def save_settings(db, event_id: str, event: dict, form, actor: str = '') -> dict:
    design = get(event)
    if design is None:
        raise DesignError("Upload a design first.")
    corner = str(form.get('qr_corner') or design['qr']['corner'])
    design = dict(design, fields=parse_fields(form, design['fields']),
                  qr={'corner': corner if corner in CORNERS else design['qr']['corner']})
    db.collection('events').document(event_id).update({FIELD: design})
    name = design['fields']['name']
    _audit(db, actor, "CERT_DESIGN_CHANGED",
           f"event {event_id}: name at {name['y']}% from the top, {name['x']}% from the left, "
           f"{name['w']}% wide, {name['size']} pt; QR {design['qr']['corner']}")
    return design


def remove(db, event_id: str, actor: str = '') -> None:
    """Back to the built-in templates. The file stays stored: certificates issued with it still use it."""
    db.collection('events').document(event_id).update({FIELD: None})
    _audit(db, actor, "CERT_DESIGN_REMOVED", f"event {event_id}")


def snapshot(event: dict) -> Optional[dict]:
    """What a certificate keeps of the design as issued."""
    design = get(event)
    if design is None:
        return None
    return {k: design[k] for k in ('image_key', 'sha256', 'orientation', 'fields', 'qr')}


def image(design: dict) -> bytes:
    from utils_storage import get_private
    return get_private(design['image_key'])


def values(name: str, data: dict) -> dict:
    """What goes in each box for one certificate."""
    return {'name': name, 'team': data.get('team') or '', 'usn': data.get('usn') or '',
            'college': data.get('institution') or data.get('college') or ''}
