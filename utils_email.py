"""
utils_email.py — SapthaEvent Email Utilities

KEY FIX: Every send is wrapped in try/except with a 10-second SMTP timeout.
Email failures are LOGGED but never crash the request.
The WORKER TIMEOUT / Internal Server Error is caused by SMTP blocking forever —
this version prevents that completely.

REQUIRED Railway Variables:
  MAIL_SERVER   = smtp.gmail.com
  MAIL_PORT     = 587
  MAIL_USE_TLS  = true
  MAIL_USER     = your-gmail@gmail.com
  MAIL_PASS     = xxxx xxxx xxxx xxxx   ← 16-char App Password (NOT Gmail login password)
  MAIL_SENDER   = SapthaEvent <your-gmail@gmail.com>
  BASE_URL      = https://your-app.up.railway.app
"""

import logging
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email              import encoders

logger = logging.getLogger(__name__)

# ── Flask-Mail helper ────────────────────────────────────────
_mail_instance = None

def init_mail(mail_obj):
    """Call this from app.py: init_mail(mail)"""
    global _mail_instance
    _mail_instance = mail_obj

def _get_mail():
    global _mail_instance
    if _mail_instance is None:
        from flask_mail import Mail
        from flask import current_app
        _mail_instance = Mail(current_app)
    return _mail_instance


# ── Core send with timeout ───────────────────────────────────

def _smtp_send(to_list: list, subject: str, html_body: str,
               text_body: str = '', attachments: list = None) -> bool:
    """
    Low-level SMTP send with a hard 10-second timeout.
    Never raises — returns True on success, False on failure.
    attachments = [{'filename': 'cert.pdf', 'data': bytes, 'mime': 'application/pdf'}]
    """
    mail_user   = os.environ.get('MAIL_USER',   '').strip()
    mail_pass   = os.environ.get('MAIL_PASS',   '').strip()
    mail_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com').strip()
    mail_port   = int(os.environ.get('MAIL_PORT', 587))
    mail_sender = os.environ.get('MAIL_SENDER', f'SapthaEvent <{mail_user}>').strip()

    if not mail_user or not mail_pass:
        logger.error("EMAIL NOT SENT — MAIL_USER or MAIL_PASS not set in Railway Variables")
        return False

    try:
        msg = MIMEMultipart('mixed')
        msg['From']    = mail_sender
        msg['To']      = ', '.join(to_list) if isinstance(to_list, list) else to_list
        msg['Subject'] = subject

        alt = MIMEMultipart('alternative')
        if text_body:
            alt.attach(MIMEText(text_body, 'plain'))
        alt.attach(MIMEText(html_body, 'html'))
        msg.attach(alt)

        # Attachments
        if attachments:
            for att in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(att['data'])
                encoders.encode_base64(part)
                part.add_header('Content-Disposition',
                                f"attachment; filename=\"{att['filename']}\"")
                part.add_header('Content-Type', att.get('mime', 'application/octet-stream'))
                msg.attach(part)

        # Connect with 10-second timeout — prevents worker timeout
        with smtplib.SMTP(mail_server, mail_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(mail_user, mail_pass)
            server.sendmail(mail_sender, to_list if isinstance(to_list, list) else [to_list],
                            msg.as_string())

        logger.info("Email sent to %s — %s", to_list, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "EMAIL AUTH FAILED — Your MAIL_PASS is wrong. "
            "Go to myaccount.google.com/apppasswords and generate a 16-char App Password. "
            "Set it as MAIL_PASS in Railway Variables."
        )
        return False
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to_list, exc)
        return False
    except TimeoutError:
        logger.error("EMAIL TIMEOUT — SMTP connection to %s:%s timed out", mail_server, mail_port)
        return False
    except Exception as exc:
        logger.error("Email send failed to %s: %s", to_list, exc)
        return False


def _base_url() -> str:
    try:
        from flask import current_app
        return current_app.config.get('BASE_URL', 'https://saptha-event-portal-production.up.railway.app')
    except Exception:
        return os.environ.get('BASE_URL', 'https://saptha-event-portal-production.up.railway.app')


def _html_wrapper(content: str, title: str = 'SapthaEvent') -> str:
    """Consistent email HTML wrapper with SNPSU branding."""
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:auto;
                background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
      <div style="background:#0d2d62;padding:24px;text-align:center;">
        <img src="https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png"
             height="36" style="display:block;margin:0 auto 10px;max-width:200px;" alt="SNPSU">
        <h2 style="color:#fff;margin:0;font-size:18px;">{title}</h2>
      </div>
      <div style="padding:28px;">
        {content}
      </div>
      <div style="background:#f8fafc;padding:16px;text-align:center;
                  border-top:1px solid #e2e8f0;">
        <p style="color:#94a3b8;font-size:11px;margin:0;">
          SapthaEvent Portal · Sapthagiri NPS University
        </p>
      </div>
    </div>"""


# ── Individual email functions ───────────────────────────────

def send_ticket_email(to_email: str, name: str, event_title: str,
                      reg_id: str, qr_bytes: bytes = None) -> bool:
    """Send registration confirmation + QR ticket."""
    base  = _base_url()
    html  = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have successfully registered for
           <strong style="color:#0d2d62;">{event_title}</strong>.</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:16px;text-align:center;margin:16px 0;">
          <p style="color:#166534;font-size:13px;margin:0 0 6px;font-weight:700;">
            Your Ticket ID
          </p>
          <p style="font-family:monospace;font-size:20px;color:#0d2d62;
                    font-weight:700;margin:0;">{reg_id}</p>
        </div>
        <p style="color:#475569;font-size:13px;">
          {'Your QR code is attached. Show it at the venue for check-in.' if qr_bytes else
           f'Show your Ticket ID at the venue for check-in.'}
        </p>
        <p style="color:#475569;font-size:13px;">
          <a href="{base}/participant/dashboard" style="color:#0d2d62;font-weight:700;">
            View your dashboard →
          </a>
        </p>
    """, f"Registration Confirmed — {event_title}")

    text = (f"Hi {name},\n\nYou are registered for {event_title}.\n"
            f"Ticket ID: {reg_id}\n\nPortal: {base}/participant/dashboard")

    attachments = []
    if qr_bytes:
        attachments.append({
            'filename': 'QR_Ticket.png',
            'data': qr_bytes,
            'mime': 'image/png',
        })

    return _smtp_send(to_email, f"✅ Registration Confirmed — {event_title}",
                      html, text, attachments or None)


def send_credentials_email(to_email: str, name: str, role: str,
                           password: str, category: str = '') -> bool:
    """Send login credentials to newly appointed staff."""
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong>
           {f'for <strong>{category}</strong> events' if category else ''}
           on the SapthaEvent Portal.</p>
        <div style="background:#e8f0fe;border-radius:10px;padding:20px;margin:16px 0;">
          <table style="width:100%;font-size:13px;">
            <tr>
              <td style="color:#475569;padding:6px 0;width:40%;">Login URL</td>
              <td style="font-weight:700;color:#0d2d62;">
                <a href="{base}/login" style="color:#0d2d62;">{base}/login</a>
              </td>
            </tr>
            <tr>
              <td style="color:#475569;padding:6px 0;">Email</td>
              <td style="font-weight:700;color:#0d2d62;">{to_email}</td>
            </tr>
            <tr>
              <td style="color:#475569;padding:6px 0;">Password</td>
              <td style="font-family:monospace;font-size:16px;font-weight:700;
                         color:#f37021;">{password}</td>
            </tr>
          </table>
        </div>
        <p style="color:#ef4444;font-size:12px;">
          ⚠️ Please change your password after first login.
        </p>
    """, f"Your SapthaEvent Login — {role}")

    text = (f"Hi {name},\n\nYou have been appointed as {role}.\n\n"
            f"Login: {base}/login\nEmail: {to_email}\nPassword: {password}\n\n"
            f"Please change your password after first login.")

    return _smtp_send(to_email, f"🔐 Your SapthaEvent Login — {role}", html, text)


def send_appointment_email(to_email: str, name: str, role: str,
                           event_title: str) -> bool:
    """Send appointment notification to existing staff."""
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong> for
           <strong>{event_title}</strong>.</p>
        <p style="color:#475569;">
          <a href="{base}/login" style="color:#f37021;font-weight:700;">
            Login to your dashboard →
          </a>
        </p>
    """, f"Appointment — {event_title}")

    text = (f"Hi {name},\n\nYou've been appointed as {role} for {event_title}.\n"
            f"Login: {base}/login")

    return _smtp_send(to_email, f"📋 Appointment — {event_title}", html, text)


def send_result_email(to_email: str, name: str, event_title: str,
                      rank: int, score: float) -> bool:
    """Send result notification to winner."""
    rank_labels = {1: '🥇 1st Place', 2: '🥈 2nd Place', 3: '🥉 3rd Place'}
    rank_text   = rank_labels.get(rank, f'Rank {rank}')
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:20px;text-align:center;margin:16px 0;">
          <p style="font-size:28px;margin:0 0 4px;">{rank_text}</p>
          <p style="color:#0d2d62;font-weight:700;margin:0;">
            Final Score: {score}
          </p>
        </div>
        <p style="color:#475569;">Congratulations on your achievement in
           <strong>{event_title}</strong>!</p>
        <p style="color:#475569;font-size:13px;">
          Your certificate has been emailed separately. Check your inbox!
        </p>
    """, f"Results — {event_title}")

    text = (f"Congratulations {name}!\n\n{rank_text} in {event_title}.\n"
            f"Final Score: {score}")

    return _smtp_send(to_email, f"🏆 Results — {event_title}", html, text)


def send_broadcast_email(to_list: list, subject: str,
                         message: str, event_title: str = '') -> bool:
    """Send broadcast message to a list of emails."""
    html = _html_wrapper(f"""
        <p style="color:#475569;font-size:14px;white-space:pre-line;line-height:1.7;">
          {message}
        </p>
    """, subject)

    # Send in batches of 10 to avoid rate limits
    success = True
    batch   = []
    for email in to_list:
        if email:
            batch.append(email)
        if len(batch) >= 10:
            ok = _smtp_send(batch, subject, html, message)
            if not ok:
                success = False
            batch = []
    if batch:
        ok = _smtp_send(batch, subject, html, message)
        if not ok:
            success = False
    return success


def send_room_assignment_email(to_email: str, name: str, event_title: str,
                               round_num: int, room: str, judge: str) -> bool:
    """Send room + judge assignment to participant."""
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">Here are your details for
           <strong>{event_title}</strong> Round {round_num}:</p>
        <div style="background:#e8f0fe;border-radius:10px;padding:16px;margin:16px 0;">
          <p style="color:#0d2d62;font-size:15px;margin:0 0 8px;">
            <strong>Room:</strong> {room}
          </p>
          <p style="color:#0d2d62;font-size:15px;margin:0;">
            <strong>Judge:</strong> {judge}
          </p>
        </div>
        <p style="color:#ef4444;font-size:13px;">
          Please be present 15 minutes before your scheduled time.
        </p>
    """, f"Round {round_num} Details — {event_title}")

    text = (f"Hi {name},\n\nRound {round_num} details for {event_title}:\n"
            f"Room: {room}\nJudge: {judge}")

    return _smtp_send(to_email, f"📍 Round {round_num} Details — {event_title}", html, text)