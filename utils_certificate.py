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

    # 1. Try local load first to avoid loopback network request issues
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(base_dir, 'static', 'snpsu-logo.png')
        if os.path.exists(local_path):
            _logo_cache = ImageReader(local_path)
            logger.info("College logo loaded locally: %s", local_path)
            return _logo_cache
    except Exception as exc:
        logger.warning("Local logo load failed, will try remote fallback: %s", exc)

    # 2. Remote fallback
    logo_url = os.environ.get('COLLEGE_LOGO_URL', '').strip()
    if not logo_url:
        from utils_email import _base_url
        logo_url = f"{_base_url().rstrip('/')}/static/snpsu-logo.png"

    try:
        import urllib.request
        req = urllib.request.Request(logo_url,
                                     headers={'User-Agent': 'SapthaEvent/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310
            data = resp.read()
        buf = io.BytesIO(data)
        buf.seek(0)
        _logo_cache = ImageReader(buf)
        logger.info("College logo loaded from remote: %s", logo_url)
        return _logo_cache
    except Exception as exc:
        logger.warning("Logo load failed (%s): %s", logo_url, exc)
        return None


def _get_cert_logo() -> Optional[ImageReader]:
    """Loads the colored snpsu-logo.jpg for light-background certificates."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(base_dir, 'static', 'snpsu-logo.jpg')
        if os.path.exists(local_path):
            logger.info("Colored college logo loaded locally: %s", local_path)
            return ImageReader(local_path)
    except Exception as exc:
        logger.warning("Local colored logo load failed, using fallback: %s", exc)
    return _get_logo()



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
    """
    Generates an official Sapthagiri NPS University certificate PDF in landscape A4.
    Design inspired by the actual university certificate:
      - Navy / gold / purple color palette
      - Decorative zigzag + diagonal corner accents
      - University logo top-right
      - Gold medallion top-left corner
      - Three authority signature blocks
      - QR verification code bottom-right
    """
    import math
    import hashlib

    # ── Verification hash ──────────────────────────────────────────────────────
    data_to_hash = f"{reg_id}:{student_name}:{event_title}:{cert_type}:{rank}:{score}"
    verification_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

    try:
        from flask import current_app
        _db = current_app.db if (current_app and hasattr(current_app, 'db')) else None
        if not _db:
            from models import db as _db
        if _db:
            _db.collection('verified_certificates').document(verification_hash).set({
                'hash': verification_hash, 'reg_id': reg_id,
                'student_name': student_name, 'event_title': event_title,
                'cert_type': cert_type, 'rank': rank, 'score': score,
                'issued_at': datetime.now().isoformat(),
                'college_name': college_name, 'status': 'Verified'
            })
    except Exception as exc:
        logger.warning("Failed to store verified certificate record: %s", exc)

    # ── Canvas setup ───────────────────────────────────────────────────────────
    buf  = io.BytesIO()
    W, H = landscape(A4)          # 841.89 × 595.28 pt
    c    = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    CX   = W / 2

    # ── Palette (matches official SNPSU certificate) ───────────────────────────
    NAVY        = HexColor('#0c1240')   # deep navy — main text, borders
    PURPLE      = HexColor('#4a1a6e')   # purple — headings
    GOLD        = HexColor('#c9a020')   # gold — accents, lines, medals
    GOLD_LIGHT  = HexColor('#e8c84a')   # lighter gold — shimmer
    GOLD_DARK   = HexColor('#9a7a10')   # darker gold — shadows
    MAROON      = HexColor('#6b1a1a')   # maroon — for winners
    CREAM       = HexColor('#fffdf5')   # warm cream background
    BORDER_DARK = HexColor('#1a2557')   # border navy
    SILVER      = HexColor('#94a3b8')   # light gray for small text

    # ── 1. Warm cream background ───────────────────────────────────────────────
    c.setFillColor(CREAM)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── 2. Outer decorative border (double-line navy) ──────────────────────────
    margin = 18
    c.setStrokeColor(NAVY); c.setLineWidth(2.5)
    c.rect(margin, margin, W - 2*margin, H - 2*margin, fill=0, stroke=1)
    c.setStrokeColor(GOLD); c.setLineWidth(1.0)
    c.rect(margin+5, margin+5, W - 2*(margin+5), H - 2*(margin+5), fill=0, stroke=1)

    # ── 3. Diagonal corner accent blocks (like physical cert) ─────────────────
    def _corner_triangle(x1, y1, x2, y2, x3, y3, fill_color):
        c.saveState()
        c.setFillColor(fill_color)
        p = c.beginPath()
        p.moveTo(x1, y1); p.lineTo(x2, y2); p.lineTo(x3, y3)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.restoreState()

    tri_size = 68
    # Top-left corner diagonal
    _corner_triangle(margin, H-margin,
                     margin+tri_size, H-margin,
                     margin, H-margin-tri_size, NAVY)
    # Bottom-right corner diagonal
    _corner_triangle(W-margin, margin,
                     W-margin-tri_size, margin,
                     W-margin, margin+tri_size, NAVY)
    # Small gold accent at bottom-left
    _corner_triangle(margin, margin,
                     margin+28, margin,
                     margin, margin+28, GOLD)
    # Small gold accent at top-right
    _corner_triangle(W-margin, H-margin,
                     W-margin-28, H-margin,
                     W-margin, H-margin-28, GOLD)

    # ── 4. Zigzag / notched right edge accent (like cert photo) ───────────────
    # Right side decorative notch blocks
    notch_x = W - margin - 5
    for i in range(5):
        ny = margin + 30 + i * 28
        c.setFillColor(NAVY if i % 2 == 0 else GOLD)
        pts = [(notch_x, ny), (notch_x + 18, ny + 14), (notch_x, ny + 28)]
        c.saveState()
        p = c.beginPath()
        p.moveTo(*pts[0]); p.lineTo(*pts[1]); p.lineTo(*pts[2]); p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.restoreState()
    # Left side notches (mirrored)
    notch_lx = margin + 5
    for i in range(5):
        ny = H - margin - 30 - i * 28
        c.setFillColor(NAVY if i % 2 == 0 else GOLD)
        pts = [(notch_lx, ny), (notch_lx - 18, ny - 14), (notch_lx, ny - 28)]
        c.saveState()
        p = c.beginPath()
        p.moveTo(*pts[0]); p.lineTo(*pts[1]); p.lineTo(*pts[2]); p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.restoreState()

    # ── 5. Gold decorative medallion — top-left ────────────────────────────────
    medal_cx = margin + 56
    medal_cy = H - margin - 56

    # Outer gold starburst rays
    for i in range(16):
        angle = math.radians(i * 22.5)
        r_outer = 38
        r_inner = 28
        x1 = medal_cx + r_inner * math.cos(angle)
        y1 = medal_cy + r_inner * math.sin(angle)
        x2 = medal_cx + r_outer * math.cos(angle + math.radians(11.25))
        y2 = medal_cy + r_outer * math.sin(angle + math.radians(11.25))
        x3 = medal_cx + r_inner * math.cos(angle + math.radians(22.5))
        y3 = medal_cy + r_inner * math.sin(angle + math.radians(22.5))
        c.saveState()
        c.setFillColor(GOLD)
        p = c.beginPath()
        p.moveTo(x1, y1); p.lineTo(x2, y2); p.lineTo(x3, y3); p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.restoreState()

    # Medal circle layers
    c.setFillColor(GOLD_DARK); c.circle(medal_cx, medal_cy, 26, fill=1, stroke=0)
    c.setFillColor(GOLD);      c.circle(medal_cx, medal_cy, 22, fill=1, stroke=0)
    c.setFillColor(GOLD_LIGHT);c.circle(medal_cx, medal_cy, 17, fill=1, stroke=0)
    c.setFillColor(NAVY);      c.circle(medal_cx, medal_cy, 12, fill=1, stroke=0)
    # "S" monogram on medal
    c.setFillColor(GOLD); c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(medal_cx, medal_cy - 4, 'S')

    # ── 6. Gold decorative corner rosette — bottom-left ────────────────────────
    rose_cx = margin + 38; rose_cy = margin + 38
    c.setFillColor(GOLD_DARK); c.circle(rose_cx, rose_cy, 16, fill=1, stroke=0)
    c.setFillColor(GOLD);      c.circle(rose_cx, rose_cy, 12, fill=1, stroke=0)
    c.setFillColor(CREAM);     c.circle(rose_cx, rose_cy,  7, fill=1, stroke=0)
    c.setFillColor(GOLD);      c.circle(rose_cx, rose_cy,  4, fill=1, stroke=0)

    # ── 7. University logo — top-right ─────────────────────────────────────────
    CONTENT_LEFT  = margin + 86
    CONTENT_RIGHT = W - margin - 26
    logo = _get_cert_logo()
    if logo:
        logo_w, logo_h = 210, 56
        logo_x = CONTENT_RIGHT - logo_w
        logo_y = H - margin - 12 - logo_h
        try:
            c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h,
                        preserveAspectRatio=True)
    else:
        # Fallback typography only if logo image cannot load
        c.setFillColor(PURPLE); c.setFont('Helvetica-Bold', 11)
        c.drawRightString(CONTENT_RIGHT, H - margin - 18, 'SAPTHAGIRI NPS UNIVERSITY')
        c.setFillColor(NAVY); c.setFont('Helvetica', 8.5)
        c.drawRightString(CONTENT_RIGHT, H - margin - 30, 'School of Engineering & Technology')

    # ── 8. Gold horizontal divider under header ────────────────────────────────
    divider_y = H - margin - 78
    c.setStrokeColor(GOLD); c.setLineWidth(1.8)
    c.line(CONTENT_LEFT, divider_y, CONTENT_RIGHT, divider_y)
    c.setStrokeColor(NAVY); c.setLineWidth(0.5)
    c.line(CONTENT_LEFT, divider_y - 3, CONTENT_RIGHT, divider_y - 3)

    # ── 9. Certificate title ───────────────────────────────────────────────────
    TITLE_Y = H - margin - 118

    # "CERTIFICATE" in large bold
    c.setFillColor(PURPLE); c.setFont('Helvetica-Bold', 40)
    c.drawCentredString(CX - 10, TITLE_Y, 'CERTIFICATE')

    # Subtitle line
    if cert_type == 'winner':
        subtitle = f'OF ACHIEVEMENT  —  {["1ST", "2ND", "3RD"][min(rank-1,2)] if rank else ""} PLACE'
        c.setFillColor(GOLD_DARK)
    else:
        subtitle = 'OF APPRECIATION'
        c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 15)
    c.drawCentredString(CX - 10, TITLE_Y - 32, subtitle)

    # Gold ornamental lines flanking subtitle
    sub_w = c.stringWidth(subtitle, 'Helvetica-Bold', 15)
    c.setStrokeColor(GOLD); c.setLineWidth(1.2)
    c.line(CX - 10 - sub_w/2 - 70, TITLE_Y - 26,
           CX - 10 - sub_w/2 - 4,  TITLE_Y - 26)
    c.line(CX - 10 + sub_w/2 + 4,  TITLE_Y - 26,
           CX - 10 + sub_w/2 + 70, TITLE_Y - 26)

    # ── 10. Body text ─────────────────────────────────────────────────────────
    BODY_Y = TITLE_Y - 64

    c.setFillColor(NAVY); c.setFont('Helvetica', 11)
    c.drawCentredString(CX - 10, BODY_Y, 'This certificate is proudly presented to')

    # Recipient name (large, italic-style)
    name_disp = student_name[:42] + '…' if len(student_name) > 42 else student_name
    name_fs   = 30 if len(student_name) <= 24 else (24 if len(student_name) <= 34 else 18)
    NAME_Y    = BODY_Y - 38
    c.setFillColor(PURPLE); c.setFont('Helvetica-BoldOblique', name_fs)
    c.drawCentredString(CX - 10, NAME_Y, name_disp)

    # Gold underline on name
    nw = c.stringWidth(name_disp, 'Helvetica-BoldOblique', name_fs)
    c.setStrokeColor(GOLD); c.setLineWidth(1.8)
    c.line(CX - 10 - nw/2, NAME_Y - 6, CX - 10 + nw/2, NAME_Y - 6)

    # Dept / participation line
    date_str   = event_date or datetime.now().strftime('%d %B %Y')
    evt_disp   = event_title[:60] + '…' if len(event_title) > 60 else event_title
    evt_fs     = 13 if len(event_title) <= 44 else 11

    if cert_type == 'winner':
        line1 = f'in recognition of their outstanding performance in'
    else:
        line1 = f'for their active participation in'

    c.setFillColor(NAVY); c.setFont('Helvetica', 11)
    c.drawCentredString(CX - 10, NAME_Y - 28, line1)
    c.setFillColor(PURPLE); c.setFont('Helvetica-Bold', evt_fs)
    c.drawCentredString(CX - 10, NAME_Y - 46, evt_disp)
    c.setFillColor(NAVY); c.setFont('Helvetica', 10.5)
    c.drawCentredString(CX - 10, NAME_Y - 62, f'held on  {date_str}')

    # Score badge for winners
    if cert_type == 'winner' and score:
        bx = CX - 10 - 58; by = NAME_Y - 92; bw = 116; bh = 20
        c.setFillColor(NAVY)
        _draw_rounded_rect(c, bx, by, bw, bh, r=10, fill=NAVY)
        c.setFillColor(GOLD); c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(CX - 10, by + 6, f'Score: {score}')

    # ── 11. Gold horizontal divider above signatures ───────────────────────────
    SIG_DIV_Y = 112
    c.setStrokeColor(GOLD); c.setLineWidth(1.5)
    c.line(CONTENT_LEFT, SIG_DIV_Y, CONTENT_RIGHT, SIG_DIV_Y)

    # ── 12. THREE SIGNATURE BLOCKS ────────────────────────────────────────────
    # Positions: evenly spaced across the content width
    sig_y_line = SIG_DIV_Y - 18   # signature line y
    sig_y_name = SIG_DIV_Y - 30   # name text y
    sig_y_role = SIG_DIV_Y - 42   # role text y
    sig_y_dept = SIG_DIV_Y - 53   # dept text y
    sig_y_univ = SIG_DIV_Y - 63   # university text y

    # Three authority positions as per official certificate
    signatories = [
        {
            'name':  'Dr. Jayashree Nair',
            'role':  'Chief Coordinator',
            'dept':  'Director of CSE',
            'univ':  college_name,
        },
        {
            'name':  'Dr. N.C Mahendra Babu',
            'role':  'Dean — School of Engineering',
            'dept':  'and Technology',
            'univ':  college_name,
        },
        {
            'name':  'Dr. H Ramakrishna',
            'role':  'Registrar',
            'dept':  '',
            'univ':  college_name,
        },
    ]

    content_width = CONTENT_RIGHT - CONTENT_LEFT
    sig_xs = [
        CONTENT_LEFT + content_width * 0.15,
        CONTENT_LEFT + content_width * 0.50,
        CONTENT_LEFT + content_width * 0.82,
    ]
    for sig_x, sig in zip(sig_xs, signatories):
        # Draw realistic handwritten signatures above the line
        c.saveState()
        c.setLineJoin(1)
        c.setLineCap(1)
        if sig['name'] == 'Dr. Jayashree Nair':
            # Jayashree signature (black/dark-gray ink, elegant flow)
            c.setStrokeColor(HexColor('#27272a'))
            c.setLineWidth(1.3)
            p = c.beginPath()
            p.moveTo(sig_x - 30, sig_y_line + 8)
            p.curveTo(sig_x - 24, sig_y_line + 22, sig_x - 16, sig_y_line + 22, sig_x - 18, sig_y_line + 6)
            p.curveTo(sig_x - 20, sig_y_line - 2, sig_x - 28, sig_y_line - 2, sig_x - 24, sig_y_line + 10)
            p.lineTo(sig_x - 18, sig_y_line + 6)
            p.curveTo(sig_x - 14, sig_y_line + 14, sig_x - 10, sig_y_line + 14, sig_x - 12, sig_y_line + 6)
            p.lineTo(sig_x - 6, sig_y_line + 8)
            p.curveTo(sig_x - 2, sig_y_line + 15, sig_x + 2, sig_y_line + 15, sig_x, sig_y_line + 5)
            p.curveTo(sig_x + 4, sig_y_line + 12, sig_x + 8, sig_y_line + 12, sig_x + 6, sig_y_line + 5)
            p.moveTo(sig_x + 12, sig_y_line + 12)
            p.lineTo(sig_x + 15, sig_y_line + 3)
            p.lineTo(sig_x + 18, sig_y_line + 14)
            p.lineTo(sig_x + 21, sig_y_line + 3)
            p.curveTo(sig_x + 25, sig_y_line + 6, sig_x + 30, sig_y_line + 5, sig_x + 36, sig_y_line + 8)
            c.drawPath(p, fill=0, stroke=1)
        elif sig['name'] == 'Dr. N.C Mahendra Babu':
            # Dean signature (blue ink, loop-heavy, like reference image)
            c.setStrokeColor(HexColor('#2563eb'))
            c.setLineWidth(1.4)
            p = c.beginPath()
            p.moveTo(sig_x - 35, sig_y_line + 6)
            p.curveTo(sig_x - 30, sig_y_line + 22, sig_x - 22, sig_y_line + 20, sig_x - 24, sig_y_line + 4)
            p.curveTo(sig_x - 26, sig_y_line - 3, sig_x - 18, sig_y_line + 16, sig_x - 14, sig_y_line + 4)
            p.curveTo(sig_x - 10, sig_y_line + 15, sig_x - 6, sig_y_line + 15, sig_x - 8, sig_y_line + 4)
            p.curveTo(sig_x - 4, sig_y_line + 12, sig_x, sig_y_line + 12, sig_x - 2, sig_y_line + 4)
            p.moveTo(sig_x + 6, sig_y_line + 16)
            p.lineTo(sig_x + 4, sig_y_line + 2)
            p.curveTo(sig_x + 10, sig_y_line + 14, sig_x + 14, sig_y_line + 12, sig_x + 10, sig_y_line + 6)
            p.curveTo(sig_x + 14, sig_y_line + 5, sig_x + 18, sig_y_line + 3, sig_x + 13, sig_y_line + 2)
            p.curveTo(sig_x + 20, sig_y_line - 2, sig_x - 25, sig_y_line - 4, sig_x - 15, sig_y_line - 3)
            c.drawPath(p, fill=0, stroke=1)
        elif sig['name'] == 'Dr. H Ramakrishna':
            # Registrar signature (purple/indigo ink, stylized R loop, like reference image)
            c.setStrokeColor(HexColor('#4f46e5'))
            c.setLineWidth(1.5)
            p = c.beginPath()
            p.moveTo(sig_x - 26, sig_y_line + 2)
            p.lineTo(sig_x - 21, sig_y_line + 20)
            p.curveTo(sig_x - 12, sig_y_line + 22, sig_x - 10, sig_y_line + 12, sig_x - 17, sig_y_line + 9)
            p.curveTo(sig_x - 7, sig_y_line + 8, sig_x - 2, sig_y_line + 3, sig_x - 13, sig_y_line + 2)
            p.curveTo(sig_x - 4, sig_y_line + 7, sig_x, sig_y_line + 7, sig_x - 2, sig_y_line + 2)
            p.curveTo(sig_x + 3, sig_y_line + 5, sig_x + 6, sig_y_line + 5, sig_x + 5, sig_y_line + 1)
            p.moveTo(sig_x - 24, sig_y_line - 1)
            p.curveTo(sig_x - 8, sig_y_line - 3, sig_x + 12, sig_y_line - 2, sig_x + 28, sig_y_line + 1)
            c.drawPath(p, fill=0, stroke=1)
        c.restoreState()

        # Signature line
        c.setStrokeColor(NAVY); c.setLineWidth(0.8)
        c.line(sig_x - 62, sig_y_line, sig_x + 62, sig_y_line)
        # Name
        c.setFillColor(PURPLE); c.setFont('Helvetica-Bold', 8.5)
        c.drawCentredString(sig_x, sig_y_name, sig['name'])
        # Role
        c.setFillColor(NAVY); c.setFont('Helvetica', 7.5)
        c.drawCentredString(sig_x, sig_y_role, sig['role'])
        # Dept (optional second line)
        if sig['dept']:
            c.setFont('Helvetica', 7)
            c.drawCentredString(sig_x, sig_y_dept, sig['dept'])
        # University
        c.setFillColor(SILVER); c.setFont('Helvetica', 6.5)
        c.drawCentredString(sig_x, sig_y_univ, sig['univ'])


    # ── 13. QR verification code — bottom-right ───────────────────────────────
    verify_url = (f"{base_url.rstrip('/')}/verify/{verification_hash}"
                  if base_url else f"/verify/{verification_hash}")
    try:
        qr_img  = _qr_reader(verify_url)
        qr_size = 58
        qr_x    = CONTENT_RIGHT - qr_size
        qr_y    = margin + 8
        c.setFillColor(white)
        c.rect(qr_x - 2, qr_y - 2, qr_size + 4, qr_size + 4, fill=1, stroke=0)
        c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
        c.setFillColor(SILVER); c.setFont('Helvetica', 6.5)
        c.drawCentredString(qr_x + qr_size/2, qr_y - 8, 'Scan to verify')
    except Exception as exc:
        logger.warning("QR failed: %s", exc)

    # ── 14. Footer strip ──────────────────────────────────────────────────────
    c.setFillColor(SILVER); c.setFont('Helvetica', 6.5)
    c.drawString(CONTENT_LEFT, margin + 6, f'Certificate ID: {verification_hash[:20]}…  |  Reg: {reg_id}')
    c.drawRightString(CONTENT_RIGHT - qr_size - 6, margin + 6,
                      'SapthaEvent Portal  ·  Sapthagiri NPS University  ·  Bengaluru')

    c.save()
    buf.seek(0)
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
            ok = _send_cert_email(email, name, event_title, 'winner', idx, score, pdf, reg_id)
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
            ok = _send_cert_email(email, name, event_title, 'participation', 0, 0, pdf, reg_id)

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

    # Fetch event for name-position and template settings
    x_pct, y_pct = 50, 42
    issued_by = 'Dean of Student Affairs'
    if _db:
        try:
            ev = _db.collection('events').document(event_id).get()
            if ev.exists:
                ev_data = ev.to_dict()
                x_pct, y_pct = _name_pos(ev_data)
                template_id = int(ev_data.get('cert_template_id', template_id))
                issued_by = ev_data.get('cert_issued_by', issued_by)
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
                    college_name=college_name, template_id=template_id,
                    issued_by=issued_by)
            ok = _send_cert_email(email, name, event_title, 'winner', idx, score, pdf, reg_id)
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
                    template_id=template_id, issued_by=issued_by)
            ok = _send_cert_email(email, name, event_title, 'participation', 0, 0, pdf, reg_id)

            results['participation_sent' if ok else 'participation_failed'] += 1
        except Exception as exc:
            logger.error("Participation cert for %s failed: %s", email, exc)
            results['participation_failed'] += 1

    logger.info("Custom-template certs for '%s': %s", event_title, results)
    return results
