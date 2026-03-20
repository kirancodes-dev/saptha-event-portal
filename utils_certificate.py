"""
utils_certificate.py — PDF Certificate Generator for SapthaEvent

Logo: Uses COLLEGE_LOGO_URL env var.
      Defaults to official SNPSU logo if not set.
      Colors match official branding: #0d2d62 navy, #f37021 orange.

5 Certificate Templates:
  1 = Classic Navy      (navy/orange — default SNPSU)
  2 = Tech Blue         (dark/cyan — hackathons)
  3 = Cultural Gold     (maroon/gold — cultural events)
  4 = Sports Green      (green/white — sports)
  5 = Management Purple (purple/silver — business)
"""

import io
import os
import logging
import qrcode
from datetime import datetime
from qrcode.image.pil import PilImage

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

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

_logo_cache: object = None
_logo_fetched: bool = False


def _get_logo() -> ImageReader | None:
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
        with urllib.request.urlopen(req, timeout=8) as resp:
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
    tpl     = TEMPLATES.get(template_id, TEMPLATES[1])
    buf     = io.BytesIO()
    W, H    = landscape(A4)
    c       = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    PRIMARY = HexColor(tpl['primary'])
    ACCENT  = HexColor(tpl['accent'])
    BG      = HexColor(tpl['bg'])
    TEXT_D  = HexColor(tpl['text_dark'])
    TEXT_M  = HexColor(tpl['text_mid'])
    BORDER  = HexColor(tpl['border'])
    bm      = 14

    # Background
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    style = tpl['style']
    if style == 'tech':
        c.setStrokeColor(HexColor('#e2e8f0')); c.setLineWidth(0.3)
        for x in range(0, int(W), 30): c.line(x, 0, x, H)
        for y in range(0, int(H), 30): c.line(0, y, W, y)
    elif style == 'cultural':
        c.setFillColor(HexColor('#fef3c7'))
        for cx2, cy2 in [(70,70),(W-70,70),(70,H-70),(W-70,H-70)]:
            c.circle(cx2, cy2, 48, fill=1, stroke=0)
    elif style == 'sports':
        c.setFillColor(HexColor('#dcfce7')); c.setLineWidth(18)
        for i in range(-8, 18):
            c.setStrokeColor(HexColor('#dcfce7'))
            c.line(i*60, 0, i*60+H, H)

    # Border frame
    _draw_rounded_rect(c, bm, bm, W-2*bm, H-2*bm,
                       r=14, fill=white, stroke=PRIMARY, lw=2.5)
    _draw_rounded_rect(c, bm+6, bm+6, W-2*(bm+6), H-2*(bm+6),
                       r=10, stroke=BORDER, lw=0.8)

    # Header bar
    header_h = 80
    hy = H - bm - header_h
    _draw_rounded_rect(c, bm, hy, W-2*bm, header_h, r=14, fill=PRIMARY)
    c.setFillColor(ACCENT)
    c.rect(bm, hy-6, W-2*bm, 6, fill=1, stroke=0)

    # Logo in header
    logo     = _get_logo()
    logo_endx = bm + 16

    if logo:
        logo_h    = 52
        logo_w    = 160   # wide logo — SNPSU logo is landscape
        logo_x    = bm + 16
        logo_y    = hy + (header_h - logo_h) / 2
        # White rounded bg for logo
        _draw_rounded_rect(c, logo_x - 4, logo_y - 4,
                           logo_w + 8, logo_h + 8,
                           r=8, fill=white)
        try:
            c.drawImage(logo, logo_x, logo_y,
                        width=logo_w, height=logo_h,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            c.drawImage(logo, logo_x, logo_y,
                        width=logo_w, height=logo_h,
                        preserveAspectRatio=True)
        logo_endx = logo_x + logo_w + 14

    # Header text
    hcx = (logo_endx + W - bm) / 2
    c.setFillColor(ACCENT)
    c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(hcx, hy + header_h - 18, college_name.upper())
    c.setFillColor(HexColor('#94a3b8'))
    c.setFont('Helvetica', 8)
    c.drawCentredString(hcx, hy + header_h - 30,
                        'Office of Student Affairs — Events Division')
    cert_title = ('CERTIFICATE  OF  ACHIEVEMENT'
                  if cert_type == 'winner'
                  else 'CERTIFICATE  OF  PARTICIPATION')
    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 17)
    c.drawCentredString(hcx, hy + 18, cert_title)

    # Left accent column
    col_w = 100
    col_x = bm + 6
    col_h = hy - bm - 12
    c.setFillColor(PRIMARY)
    c.rect(col_x, bm+6, col_w, col_h, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.rect(col_x + col_w - 6, bm+6, 6, col_h, fill=1, stroke=0)

    # Rotated event label
    c.saveState()
    c.setFillColor(white); c.setFont('Helvetica-Bold', 9)
    c.translate(col_x + col_w/2, bm+6 + col_h/2); c.rotate(90)
    lbl = (event_title[:26] + '...' if len(event_title) > 26 else event_title).upper()
    c.drawCentredString(0, 0, lbl)
    c.restoreState()

    # Rank badge
    badge_cx = col_x + col_w/2
    badge_cy = bm + 6 + col_h * 0.76
    if cert_type == 'winner' and rank in RANK_LABELS:
        rc = {1:HexColor('#fbbf24'),2:HexColor('#94a3b8'),3:HexColor('#f97316')}.get(rank, ACCENT)
        c.setFillColor(rc); c.circle(badge_cx, badge_cy, 32, fill=1, stroke=0)
        c.setFillColor(white); c.circle(badge_cx, badge_cy, 26, fill=1, stroke=0)
        c.setFillColor(rc); c.circle(badge_cx, badge_cy, 22, fill=1, stroke=0)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 16)
        c.drawCentredString(badge_cx, badge_cy+2, {1:'1ST',2:'2ND',3:'3RD'}.get(rank,''))
        c.setFont('Helvetica', 7); c.drawCentredString(badge_cx, badge_cy-9, 'PLACE')
    else:
        c.setFillColor(ACCENT); c.circle(badge_cx, badge_cy, 26, fill=1, stroke=0)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(badge_cx, badge_cy+2,  'PARTI-')
        c.drawCentredString(badge_cx, badge_cy-10, 'CIPANT')

    # Main content
    content_x  = col_x + col_w + 16
    content_w  = W - content_x - bm - 104
    content_cx = content_x + content_w / 2

    c.setFillColor(TEXT_M); c.setFont('Helvetica', 12)
    c.drawCentredString(content_cx, hy - 38, 'This is to certify that')

    c.setFillColor(TEXT_D)
    name_fs = 28 if len(student_name) <= 26 else (22 if len(student_name) <= 36 else 17)
    c.setFont('Helvetica-Bold', name_fs)
    name_disp = student_name[:36] + '...' if len(student_name) > 36 else student_name
    c.drawCentredString(content_cx, hy - 68, name_disp)

    nw = c.stringWidth(name_disp, 'Helvetica-Bold', name_fs)
    c.setStrokeColor(ACCENT); c.setLineWidth(1.5)
    c.line(content_cx - nw/2, hy-74, content_cx + nw/2, hy-74)

    c.setFillColor(TEXT_M); c.setFont('Helvetica', 12)
    if cert_type == 'winner':
        c.drawCentredString(content_cx, hy-98,
                            f'has achieved {RANK_LABELS.get(rank,"Top Place")} in')
    else:
        c.drawCentredString(content_cx, hy-98, 'has successfully participated in')

    c.setFillColor(PRIMARY)
    evt_fs = 18 if len(event_title) <= 38 else (13 if len(event_title) <= 55 else 11)
    c.setFont('Helvetica-Bold', evt_fs)
    evt_disp = event_title[:55] + '...' if len(event_title) > 55 else event_title
    c.drawCentredString(content_cx, hy-124, evt_disp)

    if cert_type == 'winner' and score:
        _draw_rounded_rect(c, content_cx-60, hy-158, 120, 22, r=11, fill=PRIMARY)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(content_cx, hy-151, f'Final Score: {score}')

    # Date + signature
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 9)
    date_str = event_date or datetime.now().strftime('%d %B %Y')
    c.drawCentredString(content_cx, bm+62, f'Date: {date_str}')

    sig_x = content_x + 20; sig_y = bm + 36
    c.setStrokeColor(TEXT_D); c.setLineWidth(0.7)
    c.line(sig_x, sig_y+12, sig_x+150, sig_y+12)
    c.setFillColor(TEXT_D); c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(sig_x+75, sig_y+2, issued_by)
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
    c.drawCentredString(sig_x+75, sig_y-8, college_name[:40])

    # QR code
    verify_url = (f"{base_url}/verify/{reg_id}" if base_url else f"/verify/{reg_id}")
    try:
        qr_img = _qr_reader(verify_url)
        qr_size = 68; qr_x = W-bm-qr_size-18; qr_y = bm+14
        c.setFillColor(white)
        c.rect(qr_x-3, qr_y-3, qr_size+6, qr_size+6, fill=1, stroke=0)
        c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
        c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
        c.drawCentredString(qr_x+qr_size/2, qr_y-9, 'Scan to verify')
    except Exception as exc:
        logger.warning("QR failed: %s", exc)

    # Footer + corners
    c.setFillColor(TEXT_M); c.setFont('Helvetica', 7)
    c.drawString(bm+12, bm+6, f'Reg ID: {reg_id}')
    c.drawRightString(W-bm-12, bm+6, 'SapthaEvent Portal')
    for cx3, cy3 in [(bm+10,bm+10),(W-bm-10,bm+10),(bm+10,H-bm-10),(W-bm-10,H-bm-10)]:
        c.setFillColor(ACCENT); c.circle(cx3, cy3, 4, fill=1, stroke=0)

    c.save(); buf.seek(0)
    return buf.read()


def _send_cert_email(to_email, student_name, event_title,
                     cert_type, rank, score, pdf_bytes) -> bool:
    try:
        from flask_mail import Message
        from flask import current_app
        from utils_email import _get_mail

        rank_labels = {1:'🥇 1st Place', 2:'🥈 2nd Place', 3:'🥉 3rd Place'}
        if cert_type == 'winner':
            subject   = f"🏆 Your Achievement Certificate — {event_title}"
            headline  = f"Congratulations! You achieved {rank_labels.get(rank, f'Rank {rank}')}"
            body_html = (f"Your <strong>Certificate of Achievement</strong> for "
                         f"<strong>{event_title}</strong> is attached.<br><br>"
                         f"<strong style='color:#0d2d62;font-size:16px;'>Final Score: {score}</strong>")
        else:
            subject   = f"🎓 Your Participation Certificate — {event_title}"
            headline  = f"Thank you for participating in {event_title}!"
            body_html = (f"Your <strong>Certificate of Participation</strong> for "
                         f"<strong>{event_title}</strong> is attached.")

        msg      = Message(subject=subject, recipients=[to_email])
        msg.html = f"""
        <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:540px;
                    margin:auto;background:#fff;border-radius:12px;overflow:hidden;
                    border:1px solid #e2e8f0;">
          <div style="background:#0d2d62;padding:28px;text-align:center;">
            <img src="https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png"
                 height="40" style="display:block;margin:0 auto 12px;" alt="SNPSU">
            <h1 style="color:#fff;font-size:20px;margin:0;">{headline}</h1>
          </div>
          <div style="padding:28px;">
            <p style="color:#475569;font-size:14px;">Dear <strong>{student_name}</strong>,</p>
            <p style="color:#475569;font-size:14px;line-height:1.7;">{body_html}</p>
            <div style="background:#f8fafc;border-radius:10px;padding:16px;
                        margin:16px 0;font-size:13px;color:#475569;">
              <strong>What to do with your certificate:</strong>
              <ul style="margin:8px 0 0;padding-left:20px;line-height:2.2;">
                <li>Download and save the attached PDF</li>
                <li>Share it on <strong>LinkedIn</strong> to showcase your achievement</li>
                <li>Scan the QR code on the certificate to verify its authenticity</li>
              </ul>
            </div>
            <p style="color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;
                      padding-top:16px;margin-top:20px;">
              Issued by SapthaEvent Portal · Sapthagiri NPS University
            </p>
          </div>
        </div>"""
        msg.body = (f"Dear {student_name},\n\n{headline}\n\n"
                    f"Your certificate for {event_title} is attached.\n\n"
                    f"Regards,\nSapthaEvent Portal\nSapthagiri NPS University")
        safe_title = event_title.replace(' ','_').replace('/','_')[:35]
        cert_label = 'Achievement' if cert_type == 'winner' else 'Participation'
        msg.attach(filename=f"Certificate_{cert_label}_{safe_title}.pdf",
                   content_type='application/pdf', data=pdf_bytes)
        _get_mail().send(msg)
        return True
    except Exception as exc:
        logger.error("Cert email to %s failed: %s", to_email, exc)
        return False


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