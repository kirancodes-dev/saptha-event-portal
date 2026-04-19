"""
utils_email.py — SapthaEvent Email (Auto-switching)

CURRENT (Railway free plan):   Set RESEND_API_KEY  → uses Resend
FUTURE  (Railway paid plan):   Remove RESEND_API_KEY → auto-falls back to Gmail SMTP

Zero code changes needed when you upgrade Railway.
Just remove RESEND_API_KEY from Railway Variables and Gmail takes over.

Railway Variables needed RIGHT NOW (free plan):
  RESEND_API_KEY = re_xxxxxxxxxxxx
  MAIL_FROM      = SapthaEvent <noreply@snpsu.edu.in>  ← after domain verified
                   or onboarding@resend.dev              ← before domain verified

Railway Variables needed LATER (paid plan) — keep these always:
  MAIL_USER      = sapthhack@gmail.com
  MAIL_PASS      = yqfktmdnvxofqvxj   (16-char App Password without spaces)
  MAIL_FROM      = SapthaEvent <sapthhack@gmail.com>

PRIORITY ORDER (auto-detected):
  1. RESEND_API_KEY is set  → Resend (works on free Railway)
  2. RESEND_API_KEY not set → Gmail SMTP (works on paid Railway)
"""

import os
import logging
import base64

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _base_url() -> str:
    try:
        from flask import current_app
        return current_app.config.get(
            'BASE_URL',
            'https://saptha-event-portal-production.up.railway.app')
    except Exception:
        return os.environ.get(
            'BASE_URL',
            'https://saptha-event-portal-production.up.railway.app')


def _from_address() -> str:
    return os.environ.get(
        'MAIL_FROM',
        f"SapthaEvent <{os.environ.get('MAIL_USER', 'sapthhack@gmail.com')}>"
    )


def _html_wrapper(content: str, title: str = 'SapthaEvent') -> str:
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:auto;
                background:#fff;border-radius:12px;overflow:hidden;
                border:1px solid #e2e8f0;">
      <div style="background:#0d2d62;padding:24px;text-align:center;">
        <img src="https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png"
             height="36" style="display:block;margin:0 auto 10px;max-width:200px;" alt="SNPSU">
        <h2 style="color:#fff;margin:0;font-size:18px;">{title}</h2>
      </div>
      <div style="padding:28px;">{content}</div>
      <div style="background:#f8fafc;padding:16px;text-align:center;
                  border-top:1px solid #e2e8f0;">
        <p style="color:#94a3b8;font-size:11px;margin:0;">
          SapthaEvent Portal · Sapthagiri NPS University
        </p>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────
# PROVIDER 1 — RESEND (used on Railway free plan)
# ─────────────────────────────────────────────────────────────

def _send_via_resend(to_email, subject: str, html: str,
                     attachments: list = None) -> bool:
    try:
        import resend
        resend.api_key = os.environ.get('RESEND_API_KEY', '')
        to_list = [to_email] if isinstance(to_email, str) else to_email
        params  = {
            'from':    _from_address(),
            'to':      to_list,
            'subject': subject,
            'html':    html,
        }
        if attachments:
            params['attachments'] = attachments
        resend.Emails.send(params)
        logger.info("Resend → %s | %s", to_list, subject)
        return True
    except Exception as exc:
        logger.error("Resend failed → %s | %s", to_email, exc)
        return False


# ─────────────────────────────────────────────────────────────
# PROVIDER 2 — GMAIL SMTP (used on Railway paid plan)
# ─────────────────────────────────────────────────────────────

def _send_via_gmail(to_email, subject: str, html: str,
                    attachments: list = None) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText
    from email.mime.base      import MIMEBase
    from email                import encoders

    mail_user = os.environ.get('MAIL_USER', '').strip()
    mail_pass = os.environ.get('MAIL_PASS', '').strip()

    if not mail_user or not mail_pass:
        logger.error("MAIL_USER or MAIL_PASS not set in Railway Variables")
        return False

    try:
        to_list = [to_email] if isinstance(to_email, str) else to_email

        msg            = MIMEMultipart('mixed')
        msg['From']    = _from_address()
        msg['To']      = ', '.join(to_list)
        msg['Subject'] = subject

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(html, 'html'))
        msg.attach(alt)

        if attachments:
            for att in attachments:
                part = MIMEBase('application', 'octet-stream')
                # Support both base64 string and raw bytes
                data = att.get('content') or att.get('data', b'')
                if isinstance(data, str):
                    data = base64.b64decode(data)
                part.set_payload(data)
                encoders.encode_base64(part)
                fname = att.get('filename') or att.get('name', 'attachment')
                part.add_header('Content-Disposition',
                                f'attachment; filename="{fname}"')
                msg.attach(part)

        # 10-second timeout — prevents gunicorn worker hang
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(mail_user, mail_pass)
            server.sendmail(mail_user, to_list, msg.as_string())

        logger.info("Gmail SMTP → %s | %s", to_list, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail auth failed. MAIL_PASS must be a 16-char App Password "
            "(no spaces). Generate at myaccount.google.com/apppasswords"
        )
        return False
    except Exception as exc:
        logger.error("Gmail SMTP failed → %s | %s", to_email, exc)
        return False


# ─────────────────────────────────────────────────────────────
# CORE SEND — auto-detects provider
# ─────────────────────────────────────────────────────────────

def _send(to_email, subject: str, html: str,
          attachments: list = None) -> bool:
    """
    Auto-detects which provider to use.
    Never raises. Returns True on success, False on failure.

    FREE PLAN  → RESEND_API_KEY is set  → uses Resend
    PAID PLAN  → RESEND_API_KEY removed → uses Gmail SMTP
    """
    if os.environ.get('RESEND_API_KEY'):
        return _send_via_resend(to_email, subject, html, attachments)
    else:
        return _send_via_gmail(to_email, subject, html, attachments)


# ─────────────────────────────────────────────────────────────
# PUBLIC EMAIL FUNCTIONS
# ─────────────────────────────────────────────────────────────

def send_ticket_email(to_email: str, name: str, event_title: str,
                      reg_id: str, qr_bytes: bytes = None) -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You are successfully registered for
           <strong style="color:#0d2d62;">{event_title}</strong>.</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:16px;text-align:center;margin:16px 0;">
          <p style="color:#166534;font-size:13px;margin:0 0 6px;font-weight:700;">
            Your Ticket ID</p>
          <p style="font-family:monospace;font-size:22px;color:#0d2d62;
                    font-weight:700;margin:0;">{reg_id}</p>
        </div>
        <p style="color:#475569;font-size:13px;">
          Show this Ticket ID at the venue for check-in.
          {'Your QR code is attached.' if qr_bytes else ''}
        </p>
        <p style="margin-top:20px;">
          <a href="{base}/participant/dashboard"
             style="background:#0d2d62;color:#fff;padding:10px 24px;
                    border-radius:8px;text-decoration:none;font-weight:700;">
            View My Dashboard →
          </a>
        </p>
    """, f"Registration Confirmed — {event_title}")

    atts = None
    if qr_bytes:
        atts = [{
            'filename': 'QR_Ticket.png',
            'name':     'QR_Ticket.png',
            'content':  base64.b64encode(qr_bytes).decode(),
            'data':     qr_bytes,
        }]
    return _send(to_email, f"✅ Registered — {event_title}", html, atts)


def send_credentials_email(to_email: str, name: str, role: str,
                           password: str, category: str = '') -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong>
           {f'for <strong>{category}</strong> events' if category else ''}.</p>
        <div style="background:#e8f0fe;border-radius:10px;padding:20px;margin:16px 0;">
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            <tr>
              <td style="color:#64748b;padding:8px 0;width:30%;">Login URL</td>
              <td><a href="{base}/login" style="color:#0d2d62;font-weight:700;">
                {base}/login</a></td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Email</td>
              <td style="font-weight:700;color:#0d2d62;">{to_email}</td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Password</td>
              <td style="font-family:monospace;font-size:20px;font-weight:700;
                         color:#f37021;letter-spacing:2px;">{password}</td>
            </tr>
          </table>
        </div>
        <p style="color:#ef4444;font-size:13px;font-weight:600;">
          ⚠️ Change your password after first login.
        </p>
    """, f"Your Login — {role}")
    return _send(to_email, f"🔐 Your SapthaEvent Login — {role}", html)


def send_appointment_email(to_email: str, name: str, role: str,
                           event_title: str) -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong>
           for <strong>{event_title}</strong>.</p>
        <p style="margin-top:20px;">
          <a href="{base}/login"
             style="background:#f37021;color:#fff;padding:10px 24px;
                    border-radius:8px;text-decoration:none;font-weight:700;">
            Login to Dashboard →
          </a>
        </p>
    """, f"Appointment — {event_title}")
    return _send(to_email, f"📋 Appointed as {role} — {event_title}", html)


def send_result_email(to_email: str, name: str, event_title: str,
                      rank: int, score: float) -> bool:
    rank_labels = {1: '🥇 1st Place', 2: '🥈 2nd Place', 3: '🥉 3rd Place'}
    rank_text   = rank_labels.get(rank, f'Rank {rank}')
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:24px;text-align:center;margin:16px 0;">
          <p style="font-size:32px;margin:0 0 6px;">{rank_text}</p>
          <p style="color:#0d2d62;font-weight:700;font-size:16px;margin:0;">
            Final Score: {score}</p>
        </div>
        <p style="color:#475569;">Congratulations in
           <strong>{event_title}</strong>!
           Your certificate is in a separate email.</p>
    """, f"🏆 Results — {event_title}")
    return _send(to_email, f"🏆 Results — {event_title}", html)


def send_broadcast_email(to_list: list, subject: str,
                         message: str, event_title: str = '') -> bool:
    html = _html_wrapper(f"""
        <div style="color:#475569;font-size:14px;line-height:1.8;white-space:pre-line;">
          {message}
        </div>
    """, subject)
    success = True
    for email in to_list:
        if email:
            if not _send(email, subject, html):
                success = False
    return success


def _send_cert_email(to_email: str, student_name: str,
                     event_title: str, cert_type: str,
                     rank: int, score: float,
                     pdf_bytes: bytes) -> bool:
    rank_labels = {1: '🥇 1st Place', 2: '🥈 2nd Place', 3: '🥉 3rd Place'}
    if cert_type == 'winner':
        subject  = f"🏆 Your Achievement Certificate — {event_title}"
        headline = f"Congratulations! {rank_labels.get(rank, f'Rank {rank}')}"
        body     = (f"Your Certificate of Achievement for "
                    f"<strong>{event_title}</strong> is attached.<br>"
                    f"<strong style='color:#0d2d62;'>Score: {score}</strong>")
    else:
        subject  = f"🎓 Your Participation Certificate — {event_title}"
        headline = "Thank you for participating!"
        body     = (f"Your Certificate of Participation for "
                    f"<strong>{event_title}</strong> is attached.")

    html  = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{student_name}</strong>,</p>
        <p style="color:#475569;">{body}</p>
        <ul style="color:#475569;font-size:13px;line-height:2.2;">
          <li>Download and save the PDF</li>
          <li>Share on <strong>LinkedIn</strong></li>
          <li>Scan the QR code on the certificate to verify it</li>
        </ul>
    """, headline)

    safe  = event_title.replace(' ', '_')[:35]
    label = 'Achievement' if cert_type == 'winner' else 'Participation'
    b64   = base64.b64encode(pdf_bytes).decode()
    fname = f"Certificate_{label}_{safe}.pdf"

    atts = [{'filename': fname, 'name': fname, 'content': b64, 'data': pdf_bytes}]
    return _send(to_email, subject, html, atts)


# Alias used by utils_certificate.py
def _get_mail():
    return None