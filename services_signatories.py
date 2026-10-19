"""
services_signatories.py — each event's certificate signatories (UPG-123).

An event has 1 to 3 signatories, each with a name, a title, an order (left to
right on the certificate) and a signature image. The image must be a PNG or
JPG of at most 1 MB on a white or transparent background; it is made
transparent, trimmed to the signature and resized, then stored privately
(utils_storage.put_private), never at a public URL. Changes are audit-logged.
A certificate keeps the signatories it was issued with (services_certificates
puts a snapshot on the record), so a later change affects only certificates
issued afterwards. A SPOC can copy the signatories of one of their own events.
"""
import io
import logging
import uuid
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_SIGNATORIES = 3
MAX_BYTES = 1024 * 1024
MAX_SIZE = (600, 200)
FIELD = 'cert_signatories'


class SignatoryError(ValueError):
    pass


def process_signature(data: bytes) -> bytes:
    """A clean, transparent, trimmed PNG of the signature, or SignatoryError
    saying what's wrong with the upload."""
    from PIL import Image, UnidentifiedImageError
    if not data:
        raise SignatoryError("Choose a signature image to upload.")
    if len(data) > MAX_BYTES:
        raise SignatoryError("The signature image must be 1 MB or smaller.")
    try:
        image = Image.open(io.BytesIO(data))
        kind = image.format
        image.load()
    except (UnidentifiedImageError, OSError):
        raise SignatoryError("Upload the signature as a PNG or JPG image.")
    if kind not in ('PNG', 'JPEG'):
        raise SignatoryError("Upload the signature as a PNG or JPG image.")
    image = image.convert('RGBA')
    w, h = image.size
    if w < 20 or h < 10:
        raise SignatoryError("The signature image is too small; upload a clearer scan.")

    # The background: the image's edges must be white (or near it) or transparent
    px = image.load()
    edge = [px[x, y] for x in range(w) for y in (0, h - 1)] + [px[x, y] for y in range(h) for x in (0, w - 1)]

    def background(p):
        return p[3] < 16 or min(p[:3]) >= 225
    if sum(1 for p in edge if background(p)) < 0.9 * len(edge):
        raise SignatoryError("The signature needs a white or transparent background (sign on plain white paper).")

    # Make the background transparent and keep only the ink
    cleaned = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out = cleaned.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a >= 16 and min(r, g, b) < 225:
                out[x, y] = (r, g, b, a)
    box = cleaned.getbbox()
    if not box:
        raise SignatoryError("No signature found in the image: it's blank or too light.")
    cleaned = cleaned.crop(box)
    cleaned.thumbnail(MAX_SIZE)
    buf = io.BytesIO()
    cleaned.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def _event(db, event_id: str) -> dict:
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        raise SignatoryError("Event not found.")
    return doc.to_dict() or {}


def listing(db, event_id: str, event: Optional[dict] = None) -> List[dict]:
    event = event if event is not None else _event(db, event_id)
    return sorted((s for s in event.get(FIELD) or [] if isinstance(s, dict)), key=lambda s: s.get('order', 0))


def ready(signatories: List[dict]) -> bool:
    """Certificates can be issued once a signatory has a signature."""
    return any(s.get('image_key') for s in signatories)


def missing_message(signatories: List[dict]) -> str:
    if not signatories:
        return "Add at least one certificate signatory (name, title and signature) before issuing certificates."
    return "Upload a signature image for at least one signatory before issuing certificates."


def _save(db, event_id: str, signatories: List[dict]) -> None:
    for i, s in enumerate(sorted(signatories, key=lambda s: s.get('order', 0)), start=1):
        s['order'] = i
    db.collection('events').document(event_id).update({FIELD: signatories})


def _audit(db, actor: str, action: str, details: str) -> None:
    from utils import log_action
    log_action(db, action, f"{actor}: {details}")


def add(db, event_id: str, *, name: str, title: str, image: bytes, order: Optional[int] = None,
        actor: str = '') -> dict:
    name, title = (name or '').strip()[:120], (title or '').strip()[:160]
    if not name or not title:
        raise SignatoryError("Give the signatory's name and title, e.g. \"Dr. A. Kumar\" and \"Principal\".")
    current = listing(db, event_id)
    if len(current) >= MAX_SIGNATORIES:
        raise SignatoryError("A certificate has at most 3 signatories; remove one first.")
    png = process_signature(image)
    from utils_storage import put_private
    sig_id = uuid.uuid4().hex
    key = put_private(png, f"signatures/{event_id}/{sig_id}.png", 'image/png')
    entry = {'id': sig_id, 'name': name, 'title': title, 'image_key': key,
             'order': order if order is not None else len(current) + 1}
    _save(db, event_id, current + [entry])
    _audit(db, actor, "CERT_SIGNATORY_ADDED", f"{name} ({title}) on event {event_id}")
    return entry


def remove(db, event_id: str, sig_id: str, actor: str = '') -> None:
    current = listing(db, event_id)
    left = [s for s in current if s.get('id') != sig_id]
    if len(left) == len(current):
        raise SignatoryError("No such signatory.")
    _save(db, event_id, left)   # the image stays stored: certificates issued with it still show it
    gone = next(s for s in current if s.get('id') == sig_id)
    _audit(db, actor, "CERT_SIGNATORY_REMOVED", f"{gone.get('name')} from event {event_id}")


def reorder(db, event_id: str, ids_in_order: List[str], actor: str = '') -> None:
    current = {s['id']: s for s in listing(db, event_id)}
    if sorted(ids_in_order) != sorted(current):
        raise SignatoryError("Give every signatory a place.")
    for i, sig_id in enumerate(ids_in_order, start=1):
        current[sig_id]['order'] = i
    _save(db, event_id, list(current.values()))
    _audit(db, actor, "CERT_SIGNATORIES_REORDERED", f"event {event_id}: {', '.join(current[i]['name'] for i in ids_in_order)}")


def copy_from(db, event_id: str, source_event_id: str, actor: str = '') -> int:
    """Copy another event's signatories (the images too, stored under this event)."""
    from utils_storage import get_private, put_private
    source = listing(db, source_event_id)
    if not source:
        raise SignatoryError("That event has no signatories to copy.")
    copied = []
    for s in source[:MAX_SIGNATORIES]:
        sig_id = uuid.uuid4().hex
        key = ''
        if s.get('image_key'):
            key = put_private(get_private(s['image_key']), f"signatures/{event_id}/{sig_id}.png", 'image/png')
        copied.append({'id': sig_id, 'name': s.get('name'), 'title': s.get('title'), 'image_key': key,
                       'order': s.get('order', len(copied) + 1)})
    _save(db, event_id, copied)
    _audit(db, actor, "CERT_SIGNATORIES_COPIED", f"event {event_id} from event {source_event_id} ({len(copied)})")
    return len(copied)


def image_bytes(signatories: List[dict]) -> dict:
    """{signatory id: PNG bytes} for drawing them on a certificate."""
    from utils_storage import get_private
    out = {}
    for s in signatories:
        if s.get('image_key'):
            try:
                out[s['id']] = get_private(s['image_key'])
            except Exception as exc:
                logger.warning("Signature %s not read: %s", s.get('id'), exc)
    return out
