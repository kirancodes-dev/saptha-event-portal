"""
services_badges.py — name badges for an event (UPG-158).

A4 sheets of 8 badges (2 × 4, 105 × 74 mm each, cut along the lines), or
one badge on its own page for printing at the door after a check-in.

A participant's badge has their name, their college (faculty and external
participants) or department (students), their participant type or team, the
university logo, the event and the QR of the registration's signed ticket
token, which every scanner accepts. A team's members each get a badge with
the team's QR. Staff, judges and volunteers get role badges without a QR.

Only a name, an institution or department and a role are printed: never a
phone number or an email.
"""
import io
import os
from typing import Dict, List, Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

ROOT = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(ROOT, 'static', 'snpsu-logo.png')
NAVY, GOLD, INK, MUTED = HexColor('#0b2545'), HexColor('#d4af37'), HexColor('#111827'), HexColor('#4b5563')
ROLE_COLOURS = {'Participant': NAVY, 'Judge': HexColor('#7c2d12'), 'Volunteer': HexColor('#166534'),
                'Staff': HexColor('#4c1d95'), 'Coordinator': HexColor('#4c1d95')}
BADGE_W, BADGE_H = 105 * mm, A4[1] / 4
PER_PAGE = 8
TYPE_LABELS = {'student': 'Student', 'faculty': 'Faculty', 'external': 'Guest'}
NOT_ATTENDING = ('cancelled', 'pending_payment', 'pending payment', 'rejected', 'waitlisted')


def _entry_ok(reg: dict, event: dict) -> bool:
    from routes_ticket import payment_allows_entry
    status = str(reg.get('status') or '').strip().lower()
    return status not in NOT_ATTENDING and payment_allows_entry(reg, event)


def participant_badges(reg_id: str, reg: dict, event: dict, qr_text: str, profile: Optional[dict] = None) -> List[Dict]:
    """One badge for each person on the registration (the lead, then members)."""
    from services_export import department_and_year
    from services_participants import type_of
    ptype = type_of(reg)
    if ptype in ('faculty', 'external'):
        line = str(reg.get('institution') or '')
    else:
        line = department_and_year(reg, profile)[0]
    team = reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''
    role = f"Team {team}" if team else TYPE_LABELS.get(ptype, 'Participant')
    names = [reg.get('lead_name') or '']
    lead = (reg.get('lead_email') or '').lower()
    names += [m.get('name') or '' for m in reg.get('members') or []
              if (m.get('email') or '').lower() != lead and (m.get('name') or '').strip()
              and str(m.get('role') or '').lower() != 'lead']
    return [{'name': n, 'line': line, 'role': role, 'kind': 'Participant', 'qr': qr_text, 'reg_id': reg_id}
            for n in names if n.strip()]


def staff_badges(db, event: dict) -> List[Dict]:
    """Role badges for the event's staff, judges and volunteers (no QR)."""
    out, seen = [], set()
    for person in event.get('staff') or []:
        email = str(person.get('email') or '').lower()
        if not email or email in seen:
            continue
        seen.add(email)
        role = str(person.get('role') or 'Staff')
        kind = 'Judge' if 'judge' in role.lower() else 'Volunteer' if 'volunteer' in role.lower() else 'Staff'
        name = person.get('name') or ''
        dept = ''
        doc = db.collection('users').document(email).get()
        if doc.exists:
            prof = doc.to_dict() or {}
            name = name or prof.get('name', '')
            dept = prof.get('department') or prof.get('institution') or ''
        out.append({'name': name or 'Event staff', 'line': dept, 'role': kind.upper(), 'kind': kind,
                    'qr': '', 'reg_id': ''})
    return out


def event_badges(db, event_id: str, event: dict, token_for) -> List[Dict]:
    """Every attending registration's people, in name order, then the staff."""
    regs = [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    people = []
    for reg_id, reg in sorted(regs, key=lambda x: str(x[1].get('lead_name') or '').lower()):
        if _entry_ok(reg, event):
            people += participant_badges(reg_id, reg, event, token_for(reg_id, reg))
    return people + staff_badges(db, event)


# ── Drawing ────────────────────────────────────────────────────────────────

def _fit(c, text: str, font: str, size: float, width: float, smallest: float = 8) -> float:
    while size > smallest and c.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _clip(c, text: str, font: str, size: float, width: float) -> str:
    while text and c.stringWidth(text, font, size) > width:
        text = text[:-2] + '…' if len(text) > 2 else ''
    return text


def _qr_image(text: str):
    import qrcode
    img = qrcode.make(text, box_size=6, border=1)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ImageReader(buf)


def _draw(c, badge: dict, event: dict, x: float, y: float) -> None:
    pad = 5 * mm
    colour = ROLE_COLOURS.get(badge['kind'], NAVY)
    c.setStrokeColor(HexColor('#cbd5e1'))
    c.setLineWidth(0.5)
    c.setDash(2, 2)
    c.rect(x, y, BADGE_W, BADGE_H)                      # the cutting line
    c.setDash()
    top = y + BADGE_H
    if os.path.exists(LOGO):
        c.drawImage(LOGO, x + pad, top - pad - 9 * mm, width=26 * mm, height=9 * mm,
                    preserveAspectRatio=True, mask='auto', anchor='sw')
    title = str(event.get('title') or '')
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 8)
    c.drawRightString(x + BADGE_W - pad, top - pad - 4 * mm, _clip(c, title, 'Helvetica-Bold', 8, BADGE_W - 38 * mm))
    when = ' · '.join(v for v in (str(event.get('date') or '')[:10], str(event.get('venue') or '')) if v)
    c.setFont('Helvetica', 7)
    c.drawRightString(x + BADGE_W - pad, top - pad - 8 * mm, _clip(c, when, 'Helvetica', 7, BADGE_W - 38 * mm))

    qr_size = 30 * mm if badge['qr'] else 0
    text_w = BADGE_W - 2 * pad - (qr_size + 3 * mm if qr_size else 0)
    name = badge['name']
    size = _fit(c, name, 'Helvetica-Bold', 20, text_w, 10)
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', size)
    c.drawString(x + pad, top - 30 * mm, _clip(c, name, 'Helvetica-Bold', size, text_w))
    if badge['line']:
        c.setFillColor(MUTED)
        c.setFont('Helvetica', 10)
        c.drawString(x + pad, top - 37 * mm, _clip(c, badge['line'], 'Helvetica', 10, text_w))
    if qr_size:
        c.drawImage(_qr_image(badge['qr']), x + BADGE_W - pad - qr_size, y + 13 * mm, qr_size, qr_size)

    # The role strip along the bottom
    c.setFillColor(colour)
    c.rect(x, y, BADGE_W, 10 * mm, stroke=0, fill=1)
    c.setFillColor(GOLD if badge['kind'] == 'Participant' else HexColor('#ffffff'))
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(x + BADGE_W / 2, y + 3.5 * mm, _clip(c, badge['role'], 'Helvetica-Bold', 11, BADGE_W - 2 * pad))


def render(badges: List[Dict], event: dict, single: bool = False) -> bytes:
    """A4 PDF: 8 badges a page, or one badge on its own page."""
    out = io.BytesIO()
    c = rl_canvas.Canvas(out, pagesize=A4)
    c.setTitle(f"Badges — {event.get('title', '')}")
    if single:
        for badge in badges:
            _draw(c, badge, event, (A4[0] - BADGE_W) / 2, A4[1] - BADGE_H - 15 * mm)
            c.showPage()
    else:
        for i, badge in enumerate(badges):
            slot = i % PER_PAGE
            if i and slot == 0:
                c.showPage()
            _draw(c, badge, event, (slot % 2) * BADGE_W, A4[1] - (slot // 2 + 1) * BADGE_H)
    if not badges:
        c.setFont('Helvetica', 12)
        c.drawString(20 * mm, A4[1] - 30 * mm, 'No confirmed registrations yet.')
    c.save()
    return out.getvalue()
