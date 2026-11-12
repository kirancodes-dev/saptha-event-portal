"""
services_event_documents.py — documents the organiser gives registered teams
(UPG-239).

The hosting SPOC adds a document to an event: a title, the instructions they
type, and a PDF (for example an undertaking form), or only one of the two. It
shows on the student portal of everyone registered (the team lead and the
members), who reads the instructions and downloads the PDF. What to do with
it (sign it, bring it to a room) is in the SPOC's own instructions; the app
adds nothing to them.

Stored on the event as `documents`: a list of
{id, title, instructions, pdf_key, pdf_name, pdf_size, created_at, created_by}.
The PDF is a private file, handed out only through the app.
"""
import datetime
import re
import uuid

PDF_MB = 10
TITLE_MAX = 150
INSTRUCTIONS_MAX = 5000
MAX_DOCUMENTS = 20


def documents(event: dict) -> list:
    items = (event or {}).get('documents')
    return [d for d in items if isinstance(d, dict) and d.get('id')] if isinstance(items, list) else []


def find(event: dict, doc_id: str):
    return next((d for d in documents(event) if d.get('id') == str(doc_id or '')), None)


def _pdf_error(raw: bytes) -> str:
    if len(raw) > PDF_MB * 1024 * 1024:
        return f"The PDF is larger than {PDF_MB} MB."
    if not raw.startswith(b'%PDF-'):
        return "That file isn't a PDF. Save it as a PDF and upload it again."
    return ''


def safe_name(name: str) -> str:
    """A download name with no quotes, slashes or other odd characters."""
    base = re.sub(r'[^\w.\- ]', '', str(name or '').rsplit('/', 1)[-1].rsplit('\\', 1)[-1]).strip()
    if not base.lower().endswith('.pdf'):
        base = (base or 'document') + '.pdf'
    return base[-120:]


def add(db, event_id: str, event: dict, *, title: str, instructions: str, pdf: bytes = b'',
        pdf_name: str = '', by: str = '') -> tuple:
    """(ok, message). Needs a title and the instructions, a PDF, or both."""
    title = ' '.join(str(title or '').split())[:TITLE_MAX]
    instructions = str(instructions or '').replace('\r\n', '\n').strip()
    pdf = pdf or b''
    if not title:
        return False, "Give the document a title, for example “Undertaking form”."
    if not instructions and not pdf:
        return False, "Type the instructions, choose a PDF, or both."
    if len(instructions) > INSTRUCTIONS_MAX:
        return False, f"The instructions are longer than {INSTRUCTIONS_MAX} characters."
    items = documents(event)
    if len(items) >= MAX_DOCUMENTS:
        return False, f"An event can have {MAX_DOCUMENTS} documents; remove one first."
    if pdf:
        error = _pdf_error(pdf)
        if error:
            return False, error
    doc_id = uuid.uuid4().hex[:12]
    item = {'id': doc_id, 'title': title, 'instructions': instructions,
            'pdf_key': '', 'pdf_name': '', 'pdf_size': 0,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'created_by': by}
    if pdf:
        from utils_storage import put_private
        item['pdf_key'] = put_private(pdf, f"events/{event_id}/documents/{doc_id}.pdf", 'application/pdf')
        item['pdf_name'] = safe_name(pdf_name)
        item['pdf_size'] = len(pdf)
    items.append(item)
    db.collection('events').document(str(event_id)).update({'documents': items})
    event['documents'] = items
    return True, f"“{title}” is added; registered teams see it in their portal now."


def remove(db, event_id: str, event: dict, doc_id: str) -> tuple:
    items = documents(event)
    gone = find(event, doc_id)
    if not gone:
        return False, "That document isn't on this event any more."
    items = [d for d in items if d.get('id') != gone['id']]
    db.collection('events').document(str(event_id)).update({'documents': items})
    event['documents'] = items
    return True, f"“{gone.get('title')}” is removed; teams no longer see it."


def notify_registered(db, event_id: str, event: dict, doc: dict) -> int:
    """A portal notice to each registered team's lead: a new document to read.
    No email (the daily email limit is kept for registrations). Returns how
    many were told."""
    from routes_notifications_v2 import create_notification
    told = set()
    for snap in db.collection('registrations').where('event_id', '==', str(event_id)).stream():
        reg = snap.to_dict() or {}
        if str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded'):
            continue
        lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
        if not lead or lead in told:
            continue
        try:
            create_notification(
                db, user_email=lead, notif_type='event_document',
                title=f"New from the organiser: {doc.get('title')}",
                message=f"{event.get('title', 'Your event')}: read the instructions"
                        + (" and download the PDF" if doc.get('pdf_key') else '') + " in your dashboard.",
                link='/participant/dashboard#event-documents')
            told.add(lead)
        except Exception:
            continue
    return len(told)
