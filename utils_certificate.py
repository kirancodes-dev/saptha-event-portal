"""
utils_certificate.py — PDF Certificate Generator for SapthaEvent

Two modes:
  1. Built-in ReportLab templates (5 styles)
  2. SPOC-uploaded image templates (PNG/JPG overlaid with participant name)
"""

import io
import os
import logging
import qrcode
from datetime import datetime
from typing import Optional
from qrcode.image.pil import PilImage

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

from utils_email import _send_cert_email

logger = logging.getLogger(__name__)

# Official SNPSU logo — used as default if COLLEGE_LOGO_URL not set
_DEFAULT_LOGO_URL = 'https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png'

TEMPLATES = {
    1: {'name':'Classic Navy',      'description':'Navy & orange — default SNPSU',
        'primary':'#0d2d62','accent':'#f37021','bg':'#ffffff',
        'text_dark':'#1e293b','text_mid':'#475569','border':'#0d2d62','style':'classic'},
    2: {'name':'Tech Blue',         'description':'Dark blue & cyan — hackathons',
        'primary':'#0f172a','accent':'#06b6d4','bg':'#f8fafc',
        'text_dark':'#0f172a','text_mid':'#334155','border':'#06b6d4','style':'tech'},
    3: {'name':'Cultural Gold',     'description':'Maroon & gold — cultural events',
        'primary':'#7f1d1d','accent':'#d97706','bg':'#fffbeb',
        'text_dark':'#7f1d1d','text_mid':'#92400e','border':'#d97706','style':'cultural'},
    4: {'name':'Sports Green',      'description':'Green & white — sports events',
        'primary':'#14532d','accent':'#16a34a','bg':'#f0fdf4',
        'text_dark':'#14532d','text_mid':'#166534','border':'#16a34a','style':'sports'},
    5: {'name':'Management Purple', 'description':'Purple & silver — business events',
        'primary':'#3b0764','accent':'#7c3aed','bg':'#faf5ff',
        'text_dark':'#3b0764','text_mid':'#6d28d9','border':'#7c3aed','style':'management'},
}

RANK_LABELS = {1:'1ST PLACE', 2:'2ND PLACE', 3:'3RD PLACE'}

_logo_cache: Optional[ImageReader] = None
_logo_fetched: bool = False


def _get_logo() -> Optional[ImageReader]:
    global _logo_cache, _logo_fetched
    if _logo_fetched:
        return _logo_cache
    _logo_fetched = True

    # Use custom URL if set, otherwise fall back to official SNPSU logo
    logo_url = os.environ.get('COLLEGE_LOGO_URL', _DEFAULT_LOGO_URL).strip()

    try:
        import urllib.request
        req = urllib.request.Request(logo_url,
                                     headers={'User-Agent': 'SapthaEvent/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310
            data = resp.read()
        buf = io.BytesIO(data)
        buf.seek(0)
        _logo_cache = ImageReader(buf)
        logger.info("College logo loaded: %s", logo_url)
        return _logo_cache
    except Exception as exc:
        logger.warning("Logo load failed (%s): %s", logo_url, exc)
        return None


def _qr_reader(url: str) -> ImageReader:
    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=5, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white', image_factory=PilImage)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ImageReader(buf)


def _draw_rounded_rect(c, x, y, w, h, r=8, fill=None, stroke=None, lw=1):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    p = c.beginPath()
    p.moveTo(x+r, y)
    p.lineTo(x+w-r, y)
    p.arcTo(x+w-2*r, y,       x+w, y+2*r,      startAng=-90, extent=90)
    p.lineTo(x+w, y+h-r)
    p.arcTo(x+w-2*r, y+h-2*r, x+w, y+h,        startAng=0,   extent=90)
    p.lineTo(x+r, y+h)
    p.arcTo(x,    y+h-2*r,    x+2*r, y+h,       startAng=90,  extent=90)
    p.lineTo(x, y+r)
    p.arcTo(x,    y,           x+2*r, y+2*r,    startAng=180, extent=90)
    p.close()
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()


def generate_certificate_pdf(
    student_name:  str,
    event_title:   str,
    reg_id:        str,
    cert_type:     str   = 'participation',
    rank:          int   = 0,
    score:         float = 0.0,
    event_date:    str   = '',
    base_url:      str   = '',
    college_name:  str   = 'Sapthagiri NPS University',
    issued_by:     str   = 'Dean of Student Affairs',
    template_id:   int   = 1,
) -> bytes:
    import math
    import hashlib

    data_to_hash = f"{reg_id}:{student_name}:{event_title}:{cert_type}:{rank}:{score}"
    verification_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

    try:
        from flask import current_app
        _db = current_app.db if (current_app and hasattr(current_app, 'db')) else None
        if not _db:
            from models import db as _db
        if _db:
            _db.collection('verified_certificates').document(verification_hash).set({
                'hash': verification_hash,
                'reg_id': reg_id,
                'student_name': student_name,
                'event_title': event_title,
                'cert_type': cert_type,
                'rank': rank,
                'score': score,
                'issued_at': datetime.now().isoformat(),
                'college_name': college_name,
                'status': 'Verified'
            })
    except Exception as exc:
        logger.warning("Failed to store verified certificate record: %s", exc)

    tpl     = TEMPLATES.get(template_id, TEMPLATES[1])
    buf     = io.BytesIO()
    W, H    = landscape(A4)
    c       = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    PRIMARY = HexColor(tpl['primary'])
    ACCENT  = HexColor(tpl['accent'])
    TEXT_D  = HexColor(tpl['text_dark'])
    TEXT_M  = HexColor(tpl['text_mid'])
    CX      = W / 2

    def _diamond(cx, cy, hw, hh, angle_deg=0, fill=None, stroke=None, lw=1.0):
        a = math.radians(angle_deg)
        cos_a, sin_a = math.cos(a), math.sin(a)
        pts = [
            (cx - hh * sin_a, cy + hh * cos_a),
            (cx + hw * cos_a, cy + hw * sin_a),
            (cx + hh * sin_a, cy - hh * cos_a),
            (cx - hw * cos_a, cy - hw * sin_a),
        ]
        c.saveState()
        p = c.beginPath()
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.close()
        if fill:   c.setFillColor(fill)
        if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
        c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)
        c.restoreState()

    # ── 1. White background ────────────────────────────────────────────────────
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── 2. Decorative diamond clusters (primary + accent colors) ──────────────
    pale = HexColor('#cfd8dc')
    pale2 = HexColor('#e8eaf6')

    # Left cluster — bottom-left corner
    _diamond( 52,  98, 92, 70, 12,  fill=PRIMARY)
    _diamond( 94,  58, 66, 50, -8,  fill=PRIMARY)
    _diamond( 26, 172, 58, 44, 18,  fill=ACCENT)
    _diamond(122, 136, 40, 32, -14, fill=pale,  stroke=PRIMARY, lw=1.2)
    _diamond(152,  58, 28, 22,  5,  fill=pale2, stroke=ACCENT,  lw=1.0)

    # Right cluster — top-right corner
    _diamond(W - 54,  H - 90,  80, 62, -10, fill=PRIMARY)
    _diamond(W - 100, H - 62,  56, 43,  15, fill=ACCENT)
    _diamond(W - 30,  H - 152, 40, 32,  -5, fill=pale,  stroke=PRIMARY, lw=1.2)

    # ── 3. Header — logo left, portal name right ───────────────────────────────
    logo = _get_logo()
    if logo:
        lh, lw2, lx, ly = 42, 136, 168, H - 54
        try:
            c.drawImage(logo, lx, ly, width=lw2, height=lh,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            c.drawImage(logo, lx, ly, width=lw2, height=lh,
                        preserveAspectRatio=True)
    else:
        c.setFillColor(PRIMARY); c.setFont('Helvetica-Bold', 10)
        c.drawString(168, H - 30, college_name.upper())
        c.setFillColor(TEXT_M); c.setFont('Helvetica', 8)
        c.drawString(168, H - 42, 'Office of Student Affairs')

    c.setFillColor(PRIMARY); c.setFont('Helvetica-Bold', 8)
    c.drawRightString(W - 162, H - 26, 'SapthaEvent Portal')
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 7.5)
    c.drawRightString(W - 162, H - 38, 'SNPSU — Events Division')

    # Thin horizontal rule under header
    c.setStrokeColor(HexColor('#e2e8f0')); c.setLineWidth(0.5)
    c.line(168, H - 74, W - 168, H - 74)

    # ── 4. Certificate title ───────────────────────────────────────────────────
    cert_title = ('Certificate of Achievement'
                  if cert_type == 'winner'
                  else 'Certificate of Participation')
    c.setFillColor(PRIMARY); c.setFont('Helvetica-Bold', 34)
    c.drawCentredString(CX, H - 138, cert_title)

    # ── 5. "This is to certify that" with flanking rules ──────────────────────
    sub_text = 'This is to certify that'
    sub_w    = c.stringWidth(sub_text, 'Helvetica', 12)
    sub_y    = H - 182
    c.setStrokeColor(HexColor('#cbd5e1')); c.setLineWidth(0.8)
    c.line(CX - sub_w / 2 - 85, sub_y + 5, CX - sub_w / 2 - 6, sub_y + 5)
    c.line(CX + sub_w / 2 + 6,  sub_y + 5, CX + sub_w / 2 + 85, sub_y + 5)
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 12)
    c.drawCentredString(CX, sub_y, sub_text)

    # ── 6. Recipient name + underline ─────────────────────────────────────────
    name_disp = student_name[:36] + '...' if len(student_name) > 36 else student_name
    name_fs   = 30 if len(student_name) <= 26 else (24 if len(student_name) <= 36 else 19)
    name_y    = H - 224
    c.setFillColor(TEXT_D); c.setFont('Helvetica-Bold', name_fs)
    c.drawCentredString(CX, name_y, name_disp)

    nw = c.stringWidth(name_disp, 'Helvetica-Bold', name_fs)
    c.setStrokeColor(ACCENT); c.setLineWidth(2)
    c.line(CX - nw / 2, name_y - 7, CX + nw / 2, name_y - 7)

    # ── 7. Body description ────────────────────────────────────────────────────
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 11.5)
    body_y = H - 261
    if cert_type == 'winner':
        c.drawCentredString(CX, body_y,
                            f'has achieved {RANK_LABELS.get(rank, "Top Place")} in')
    else:
        c.drawCentredString(CX, body_y,
                            f'from {college_name} has successfully participated in')

    evt_disp = event_title[:58] + '...' if len(event_title) > 58 else event_title
    evt_fs   = 16 if len(event_title) <= 40 else (13 if len(event_title) <= 58 else 11)
    c.setFillColor(PRIMARY); c.setFont('Helvetica-Bold', evt_fs)
    c.drawCentredString(CX, body_y - 26, evt_disp)

    c.setFillColor(TEXT_M); c.setFont('Helvetica', 11)
    c.drawCentredString(CX, body_y - 48, f'organised by {college_name}.')

    if cert_type == 'winner' and score:
        _draw_rounded_rect(c, CX - 74, body_y - 84, 148, 24, r=12, fill=PRIMARY)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(CX, body_y - 76, f'Final Score: {score}')

    # ── 8. Signature ──────────────────────────────────────────────────────────
    sig_cx = CX - 80
    sig_y  = 78
    c.setStrokeColor(HexColor('#475569')); c.setLineWidth(0.7)
    c.line(sig_cx - 68, sig_y + 14, sig_cx + 68, sig_y + 14)
    c.setFillColor(TEXT_D); c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(sig_cx, sig_y + 4, issued_by)
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
    c.drawCentredString(sig_cx, sig_y - 6, college_name[:40])

    date_str = event_date or datetime.now().strftime('%d %B %Y')
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 9)
    c.drawString(sig_cx + 84, sig_y + 4, f'Date: {date_str}')

    # ── 9. QR code bottom-right ───────────────────────────────────────────────
    verify_url = f"{base_url}/verify/{verification_hash}" if base_url else f"/verify/{verification_hash}"
    try:
        qr_img  = _qr_reader(verify_url)
        qr_size = 66
        qr_x    = W - 168 - qr_size
        qr_y    = 28
        c.setFillColor(white)
        c.rect(qr_x - 3, qr_y - 3, qr_size + 6, qr_size + 6, fill=1, stroke=0)
        c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
        c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
        c.drawCentredString(qr_x + qr_size / 2, qr_y - 9, 'Scan to verify')
    except Exception as exc:
        logger.warning("QR failed: %s", exc)

    # ── 10. Footer ────────────────────────────────────────────────────────────
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
    c.drawString(168, 14, f'Reg ID: {reg_id}')
    c.drawRightString(W - 168, 14, 'SapthaEvent Portal · Sapthagiri NPS University')

    c.save(); buf.seek(0)
    return buf.read()





def generate_and_send_all_certificates(
    leaderboard:   list,
    registrations: list,
    event_title:   str,
    event_date:    str = '',
    base_url:      str = '',
    college_name:  str = 'Sapthagiri NPS University',
    template_id:   int = 1,
    top_n:         int = 3,
) -> dict:
    """
    Send ALL certificates simultaneously when SPOC publishes results:
      - Winner certs (top N) — Achievement with rank + score
      - Participation certs (all present attendees) — Participation
    """
    results = {'winner_sent':0,'winner_failed':0,
               'participation_sent':0,'participation_failed':0,'participation_skipped':0}

    # Winner certificates
    for idx, winner in enumerate(leaderboard[:top_n], start=1):
        name   = winner.get('lead_name', winner.get('team_name', 'Participant'))
        email  = winner.get('email', winner.get('lead_email', ''))
        reg_id = winner.get('reg_id', '')
        score  = winner.get('avg_score', winner.get('final_score', 0))
        if not email: results['winner_failed'] += 1; continue
        try:
            pdf = generate_certificate_pdf(
                student_name=name, event_title=event_title, reg_id=reg_id,
                cert_type='winner', rank=idx, score=score,
                event_date=event_date, base_url=base_url,
                college_name=college_name, template_id=template_id)
            ok = _send_cert_email(email, name, event_title, 'winner', idx, score, pdf)
            if ok: results['winner_sent']   += 1
            else:  results['winner_failed'] += 1
        except Exception as exc:
            logger.error("Winner cert rank %d failed: %s", idx, exc)
            results['winner_failed'] += 1

    # Participation certificates
    for reg in registrations:
        if reg.get('attendance') != 'Present':
            results['participation_skipped'] += 1; continue
        name   = reg.get('lead_name', 'Participant')
        email  = reg.get('lead_email', reg.get('email', ''))
        reg_id = reg.get('reg_id', reg.get('id', ''))
        if not email: results['participation_skipped'] += 1; continue
        try:
            pdf = generate_certificate_pdf(
                student_name=name, event_title=event_title, reg_id=reg_id,
                cert_type='participation', event_date=event_date,
                base_url=base_url, college_name=college_name, template_id=template_id)
            ok = _send_cert_email(email, name, event_title, 'participation', 0, 0, pdf)
            if ok: results['participation_sent']   += 1
            else:  results['participation_failed'] += 1
        except Exception as exc:
            logger.error("Participation cert for %s failed: %s", email, exc)
            results['participation_failed'] += 1

    logger.info("Certs for '%s': winner=%d, participation=%d, skipped=%d",
                event_title, results['winner_sent'],
                results['participation_sent'], results['participation_skipped'])
    return results


# ──────────────────────────────────────────────────────────
# IMAGE-TEMPLATE CERTIFICATE  (SPOC-uploaded PNG/JPG)
# ──────────────────────────────────────────────────────────

def generate_from_image_template(
    template_bytes: bytes,
    student_name:   str,
    reg_id:         str   = '',
    base_url:       str   = '',
    name_x_pct:     int   = 50,
    name_y_pct:     int   = 42,
    font_size:      int   = 0,   # 0 = auto-scale to image width
    font_color:     tuple = (26, 37, 87),
) -> bytes:
    """
    Overlay *student_name* onto a PNG/JPG certificate template and return
    a landscape-A4 PDF with the image as the full-page background.

    name_x_pct / name_y_pct: position of the name centred at (x%, y%)
    relative to the page, measured from the top-left corner.
    """
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    W, H = landscape(A4)

    # ── Load template ──────────────────────────────────────
    tpl_img = Image.open(io.BytesIO(template_bytes)).convert('RGB')

    # ── Calculate font size relative to template width ─────
    tpl_w, tpl_h = tpl_img.size
    if font_size <= 0:
        font_size = max(28, tpl_w // 18)

    # Try to load a system/bundled font; fall back gracefully
    _FONT_CANDIDATES = [
        '/System/Library/Fonts/Supplemental/Georgia.ttf',        # macOS
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
        '/Windows/Fonts/georgia.ttf',                            # Windows
    ]
    pil_font = None
    for path in _FONT_CANDIDATES:
        try:
            pil_font = ImageFont.truetype(path, font_size)
            break
        except (IOError, OSError):
            pass
    if pil_font is None:
        pil_font = ImageFont.load_default()

    # ── Draw name on a high-res copy ──────────────────────
    draw = ImageDraw.Draw(tpl_img)
    px = int(tpl_w * name_x_pct / 100)
    py = int(tpl_h * name_y_pct / 100)

    try:
        bbox = draw.textbbox((0, 0), student_name, font=pil_font)
        tw   = bbox[2] - bbox[0]
    except AttributeError:
        tw = draw.textlength(student_name, font=pil_font)

    # Thin shadow for readability on busy backgrounds
    shadow_col = (255, 255, 255, 180) if sum(font_color) < 382 else (0, 0, 0, 120)
    for dx, dy in ((2, 2), (-2, 2)):
        draw.text((px - tw // 2 + dx, py + dy), student_name,
                  fill=shadow_col[:3], font=pil_font)
    draw.text((px - tw // 2, py), student_name, fill=font_color, font=pil_font)

    # ── Composite into landscape-A4 PDF ──────────────────
    img_buf = io.BytesIO()
    tpl_img.save(img_buf, format='PNG', dpi=(150, 150))
    img_buf.seek(0)

    pdf_buf = io.BytesIO()
    c = rl_canvas.Canvas(pdf_buf, pagesize=landscape(A4))
    c.drawImage(ImageReader(img_buf), 0, 0, width=W, height=H,
                preserveAspectRatio=False)

    # QR verification code (small, bottom-right)
    if reg_id:
        try:
            verify_url = f"{base_url}/verify/{reg_id}" if base_url else f"/verify/{reg_id}"
            qr_img     = _qr_reader(verify_url)
            qr_size    = 54
            c.drawImage(qr_img, W - qr_size - 12, 10,
                        width=qr_size, height=qr_size)
        except Exception:
            pass

    c.save()
    pdf_buf.seek(0)
    return pdf_buf.read()


def generate_and_send_all_certificates_with_templates(
    leaderboard:   list,
    registrations: list,
    event_title:   str,
    event_id:      str,
    event_date:    str = '',
    base_url:      str = '',
    college_name:  str = 'Sapthagiri NPS University',
    template_id:   int = 1,
    top_n:         int = 3,
) -> dict:
    """
    Like generate_and_send_all_certificates but checks Firestore for
    SPOC-uploaded image templates first; falls back to built-in ReportLab
    styles when no custom template exists for a given cert type.
    """
    import base64
    try:
        from models import db as _db
    except Exception:
        _db = None

    def _load_template(cert_type: str) -> Optional[bytes]:
        if _db is None:
            return None
        try:
            doc = _db.collection('cert_templates').document(f'{event_id}_{cert_type}').get()
            if doc.exists:
                return base64.b64decode(doc.to_dict()['data'])
        except Exception as exc:
            logger.warning("Template load failed (%s): %s", cert_type, exc)
        return None

    def _name_pos(event_doc_data: dict) -> tuple[int, int]:
        pos = event_doc_data.get('cert_name_pos', {})
        return pos.get('x', 50), pos.get('y', 42)

    # Fetch event for name-position
    x_pct, y_pct = 50, 42
    if _db:
        try:
            ev = _db.collection('events').document(event_id).get()
            if ev.exists:
                x_pct, y_pct = _name_pos(ev.to_dict())
        except Exception:
            pass

    results = {'winner_sent': 0, 'winner_failed': 0,
               'participation_sent': 0, 'participation_failed': 0,
               'participation_skipped': 0}

    # ── Winner certificates ────────────────────────────────
    for idx, winner in enumerate(leaderboard[:top_n], start=1):
        name   = winner.get('lead_name', winner.get('team_name', 'Participant'))
        email  = winner.get('email', winner.get('lead_email', ''))
        reg_id = winner.get('reg_id', '')
        score  = winner.get('avg_score', winner.get('final_score', 0))
        if not email:
            results['winner_failed'] += 1
            continue
        try:
            tpl_key   = f'winner_{idx}'
            tpl_bytes = _load_template(tpl_key)
            if tpl_bytes:
                pdf = generate_from_image_template(
                    tpl_bytes, name, reg_id, base_url, x_pct, y_pct)
            else:
                pdf = generate_certificate_pdf(
                    student_name=name, event_title=event_title, reg_id=reg_id,
                    cert_type='winner', rank=idx, score=score,
                    event_date=event_date, base_url=base_url,
                    college_name=college_name, template_id=template_id)
            ok = _send_cert_email(email, name, event_title, 'winner', idx, score, pdf)
            results['winner_sent' if ok else 'winner_failed'] += 1
        except Exception as exc:
            logger.error("Winner cert rank %d failed: %s", idx, exc)
            results['winner_failed'] += 1

    # ── Participation certificates ─────────────────────────
    participation_tpl = _load_template('participation')
    for reg in registrations:
        if reg.get('attendance') != 'Present':
            results['participation_skipped'] += 1
            continue
        name   = reg.get('lead_name', 'Participant')
        email  = reg.get('lead_email', reg.get('email', ''))
        reg_id = reg.get('reg_id', reg.get('id', ''))
        if not email:
            results['participation_skipped'] += 1
            continue
        try:
            if participation_tpl:
                pdf = generate_from_image_template(
                    participation_tpl, name, reg_id, base_url, x_pct, y_pct)
            else:
                pdf = generate_certificate_pdf(
                    student_name=name, event_title=event_title, reg_id=reg_id,
                    cert_type='participation', event_date=event_date,
                    base_url=base_url, college_name=college_name,
                    template_id=template_id)
            ok = _send_cert_email(email, name, event_title, 'participation', 0, 0, pdf)
            results['participation_sent' if ok else 'participation_failed'] += 1
        except Exception as exc:
            logger.error("Participation cert for %s failed: %s", email, exc)
            results['participation_failed'] += 1

    logger.info("Custom-template certs for '%s': %s", event_title, results)
    return results
