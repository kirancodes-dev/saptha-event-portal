"""
utils_email.py — SapthaEvent Email (Auto-switching)

Railway blocks outbound SMTP (ports 465/587) at the platform level.
Use an HTTP-based provider instead — Brevo is free and works everywhere.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 RECOMMENDED (free, works on Railway):  BREVO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. Sign up free at https://brevo.com
 2. Settings → SMTP & API → API Keys → Generate
 3. In Railway Variables add:
      BREVO_API_KEY = xkeysib-xxxxxxxxxxxxxxxxxxxx
      MAIL_FROM     = SapthaEvent <sapthhack@gmail.com>

 Free tier: 300 emails/day, sends to ANYONE. No domain verification needed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FALLBACK: RESEND (free but only to verified emails)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      RESEND_API_KEY = re_xxxxxxxxxxxx

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 LAST RESORT: Gmail SMTP (blocked by Railway SMTP firewall)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      MAIL_USER = sapthhack@gmail.com
      MAIL_PASS = yqfktmdnvxofqvxj

PRIORITY ORDER (auto-detected at runtime):
  1. BREVO_API_KEY set     → Brevo HTTP API  ✅ Railway-safe, free, anyone
  2. RESEND_API_KEY set    → Resend HTTP API  ⚠️  verified emails only (free)
  3. Neither               → Gmail SMTP       ❌ blocked on Railway
"""

import os
import logging
import base64

logger = logging.getLogger(__name__)

# Last outbound send error — populated by _send_via_* on failure, read by /diag/email
LAST_EMAIL_ERROR = ""


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _base_url() -> str:
    try:
        from flask import current_app
        return current_app.config.get(
            'BASE_URL',
            'https://saptha-event-portal.xyz')
    except Exception:
        return os.environ.get(
            'BASE_URL',
            'https://saptha-event-portal.xyz')


def _from_address() -> str:
    return os.environ.get(
        'MAIL_FROM',
        f"SapthaEvent <{os.environ.get('MAIL_USER', 'sapthhack@gmail.com')}>"
    )


def _html_wrapper(content: str, title: str = 'SapthaEvent') -> str:
    logo_url = os.environ.get(
        'COLLEGE_LOGO_URL',
        'https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png'
    )
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:auto;
                background:#fff;border-radius:12px;overflow:hidden;
                border:1px solid #e2e8f0;">
      <div style="background:#1a2557;padding:28px 24px 20px;text-align:center;">
        <img src="{logo_url}"
             height="52" style="display:block;margin:0 auto 10px;max-width:240px;
             background:#fff;padding:6px 12px;border-radius:6px;" alt="Sapthagiri NPS University">
        <p style="color:#c9a227;font-size:12px;font-weight:700;margin:0 0 6px;
                  letter-spacing:0.5px;text-transform:uppercase;">
          Sapthagiri NPS University</p>
        <h2 style="color:#fff;margin:0;font-size:18px;font-weight:700;">{title}</h2>
      </div>
      <div style="padding:28px;">{content}</div>
      <div style="background:#f8fafc;padding:16px;text-align:center;
                  border-top:1px solid #e2e8f0;">
        <p style="color:#94a3b8;font-size:11px;margin:0;">
          SapthaEvent Portal &middot; Sapthagiri NPS University
        </p>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────
# PROVIDER 1 — RESEND (used on Railway free plan)
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# PROVIDER 0 — BREVO (recommended for Railway — pure HTTP, no SMTP)
# Free: 300 emails/day, sends to anyone, no domain verification needed.
# ─────────────────────────────────────────────────────────────

def _send_via_brevo(to_email, subject: str, html: str,
                    attachments: list = None) -> bool:
    global LAST_EMAIL_ERROR
    try:
        import urllib.request, json as _json

        api_key  = os.environ.get('BREVO_API_KEY', '')
        from_raw = _from_address()

        # Parse "Name <email>" or plain email
        if '<' in from_raw and '>' in from_raw:
            from_name  = from_raw[:from_raw.index('<')].strip().strip('"')
            from_email = from_raw[from_raw.index('<')+1:from_raw.index('>')].strip()
        else:
            from_name  = 'SapthaEvent'
            from_email = from_raw.strip()

        to_list = [to_email] if isinstance(to_email, str) else to_email

        payload = {
            'sender':      {'name': from_name, 'email': from_email},
            'to':          [{'email': e} for e in to_list],
            'subject':     subject,
            'htmlContent': html,
        }

        if attachments:
            payload['attachment'] = []
            for att in attachments:
                data = att.get('content') or att.get('data', b'')
                if isinstance(data, (bytes, bytearray)):
                    data = base64.b64encode(data).decode()
                payload['attachment'].append({
                    'name':    att.get('filename') or att.get('name', 'attachment'),
                    'content': data,
                })

        body = _json.dumps(payload).encode('utf-8')
        req  = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=body,
            headers={
                'accept':       'application/json',
                'api-key':      api_key,
                'content-type': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            status = resp.status
            if status not in (200, 201):
                raise RuntimeError(f"Brevo HTTP {status}")

        logger.info("Brevo → %s | %s", to_list, subject)
        return True

    except Exception as exc:
        LAST_EMAIL_ERROR = f"Brevo: {exc}"
        logger.error("Brevo failed → %s | %s", to_email, exc)
        return False


def _send_via_resend(to_email, subject: str, html: str,
                     attachments: list = None) -> bool:
    global LAST_EMAIL_ERROR
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
        LAST_EMAIL_ERROR = f"Resend: {exc}"
        logger.error("Resend failed → %s | %s", to_email, exc)
        return False


# ─────────────────────────────────────────────────────────────
# PROVIDER 2 — GMAIL SMTP (used on Railway paid plan)
# ─────────────────────────────────────────────────────────────

def _send_via_gmail(to_email, subject: str, html: str,
                    attachments: list = None) -> bool:
    global LAST_EMAIL_ERROR
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText
    from email.mime.base      import MIMEBase
    from email.header         import Header
    from email                import encoders

    mail_user = os.environ.get('MAIL_USER', '').strip()
    # Gmail App Passwords are displayed as "xxxx xxxx xxxx xxxx" but the actual
    # credential used in SMTP is the 16 chars without spaces.
    mail_pass = os.environ.get('MAIL_PASS', '').strip().replace(' ', '')

    if not mail_user or not mail_pass:
        LAST_EMAIL_ERROR = ("Gmail: MAIL_USER or MAIL_PASS not set. "
                            "Add them in Railway Variables and redeploy.")
        logger.error(LAST_EMAIL_ERROR)
        return False

    try:
        to_list = [to_email] if isinstance(to_email, str) else to_email

        msg            = MIMEMultipart('mixed')
        msg['From']    = _from_address()
        msg['To']      = ', '.join(to_list)
        msg['Subject'] = Header(subject, 'utf-8')

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(html, 'html', 'utf-8'))
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

        smtp_host = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('MAIL_PORT', 465))
        timeout   = int(os.environ.get('MAIL_TIMEOUT', 10))

        # Port 465 → SSL directly (works on Railway Hobby).
        # Port 587 → STARTTLS (blocked by some cloud providers).
        if smtp_port == 465:
            import ssl as _ssl
            ctx = _ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port,
                                  context=ctx, timeout=timeout) as server:
                server.login(mail_user, mail_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(mail_user, mail_pass)
                server.send_message(msg)

        logger.info("Gmail SMTP → %s | %s", to_list, subject)
        return True

    except smtplib.SMTPAuthenticationError as exc:
        LAST_EMAIL_ERROR = (f"Gmail auth failed: {exc}. MAIL_PASS must be a "
                            "16-char App Password (no spaces). Generate at "
                            "myaccount.google.com/apppasswords")
        logger.error(LAST_EMAIL_ERROR)
        return False
    except Exception as exc:
        LAST_EMAIL_ERROR = f"Gmail SMTP: {exc}"
        logger.error("Gmail SMTP failed → %s | %s", to_email, exc)
        return False


# ─────────────────────────────────────────────────────────────
# CORE SEND — auto-detects provider
# ─────────────────────────────────────────────────────────────

def _send(to_email, subject: str, html: str,
          attachments: list = None) -> bool:
    """
    Priority order (first key found wins):
      1. BREVO_API_KEY  → Brevo HTTP API  (Railway-safe, free 300/day, anyone)
      2. RESEND_API_KEY → Resend HTTP API (free but verified emails only)
      3. neither        → Gmail SMTP      (blocked on Railway)
    """
    if os.environ.get('BREVO_API_KEY'):
        return _send_via_brevo(to_email, subject, html, attachments)
    if os.environ.get('RESEND_API_KEY'):
        return _send_via_resend(to_email, subject, html, attachments)
    return _send_via_gmail(to_email, subject, html, attachments)


# ─────────────────────────────────────────────────────────────
# PUBLIC EMAIL FUNCTIONS
# ─────────────────────────────────────────────────────────────

def send_registration_confirmed_email(to_email: str, name: str, event_title: str,
                                       event_date: str = '', venue: str = '',
                                       is_new_user: bool = False,
                                       raw_password: str = None) -> bool:
    """
    Sent immediately at registration. Simple confirmation — no QR, no ticket ID.
    The actual entry ticket (with QR) is sent 1 day before the event.
    """
    credentials_block = ""
    if is_new_user and raw_password:
        base = _base_url()
        credentials_block = f"""
        <div style="background:#e8f0fe;border-radius:10px;padding:16px;margin:16px 0;">
          <p style="color:#1a2557;font-weight:700;margin:0 0 10px;font-size:14px;">
            🔑 Your Login Credentials</p>
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            <tr><td style="color:#64748b;padding:4px 0;width:30%;">Email</td>
                <td style="font-weight:700;color:#1a2557;">{to_email}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0;">Password</td>
                <td style="font-family:monospace;font-weight:700;color:#c9a227;
                           letter-spacing:1px;">{raw_password}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0;">Login</td>
                <td><a href="{base}/login" style="color:#1a2557;font-weight:700;">{base}/login</a></td></tr>
          </table>
          <p style="color:#ef4444;font-size:12px;margin:10px 0 0;font-weight:600;">
            ⚠️ Change your password after first login.</p>
        </div>"""
    details = ""
    if event_date:
        details += f"<tr><td style='color:#64748b;padding:4px 0;width:30%;'>Date</td><td style='font-weight:600;color:#1a2557;'>📅 {event_date}</td></tr>"
    if venue:
        details += f"<tr><td style='color:#64748b;padding:4px 0;'>Venue</td><td style='font-weight:600;color:#1a2557;'>📍 {venue}</td></tr>"
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">Your registration for
           <strong style="color:#1a2557;">{event_title}</strong> is confirmed!</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:16px;margin:16px 0;">
          <p style="color:#166534;font-size:13px;margin:0 0 10px;font-weight:700;">
            ✅ Registration Confirmed</p>
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            {details}
          </table>
        </div>
        {credentials_block}
        <p style="color:#475569;font-size:13px;">
          Your entry QR ticket will be emailed to you <strong>1 day before the event</strong>.
          Keep an eye on your inbox!
        </p>
    """, f"Registration Confirmed — {event_title}")
    return _send(to_email, f"Registration Confirmed — {event_title}", html)


def send_ticket_email(to_email: str, name: str, event_title: str,
                      reg_id: str, qr_bytes: bytes = None,
                      is_new_user: bool = False,
                      raw_password: str = None) -> bool:
    base = _base_url()
    credentials_block = ""
    if is_new_user and raw_password:
        credentials_block = f"""
        <div style="background:#e8f0fe;border-radius:10px;padding:16px;margin:16px 0;">
          <p style="color:#1a2557;font-weight:700;margin:0 0 10px;font-size:14px;">
            🔑 Your Login Credentials</p>
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            <tr><td style="color:#64748b;padding:4px 0;width:30%;">Email</td>
                <td style="font-weight:700;color:#1a2557;">{to_email}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0;">Password</td>
                <td style="font-family:monospace;font-weight:700;color:#c9a227;
                           letter-spacing:1px;">{raw_password}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0;">Login</td>
                <td><a href="{base}/login" style="color:#1a2557;font-weight:700;">
                  {base}/login</a></td></tr>
          </table>
          <p style="color:#ef4444;font-size:12px;margin:10px 0 0;font-weight:600;">
            ⚠️ Change your password after first login.</p>
        </div>"""
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You are successfully registered for
           <strong style="color:#1a2557;">{event_title}</strong>.</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                    padding:16px;text-align:center;margin:16px 0;">
          <p style="color:#166534;font-size:13px;margin:0 0 6px;font-weight:700;">
            Your Ticket ID</p>
          <p style="font-family:monospace;font-size:22px;color:#1a2557;
                    font-weight:700;margin:0;">{reg_id}</p>
        </div>
        {credentials_block}
        <p style="color:#475569;font-size:13px;">
          Show this Ticket ID at the venue for check-in.
          {'Your QR code is attached.' if qr_bytes else ''}
        </p>
        <p style="margin-top:20px;">
          <a href="{base}/participant/dashboard"
             style="background:#1a2557;color:#fff;padding:10px 24px;
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
           <strong style="color:#1a2557;">{role}</strong>
           {f'for <strong>{category}</strong> events' if category else ''}.</p>
        <div style="background:#e8f0fe;border-radius:10px;padding:20px;margin:16px 0;">
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            <tr>
              <td style="color:#64748b;padding:8px 0;width:30%;">Login URL</td>
              <td><a href="{base}/login" style="color:#1a2557;font-weight:700;">
                {base}/login</a></td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Email</td>
              <td style="font-weight:700;color:#1a2557;">{to_email}</td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Password</td>
              <td style="font-family:monospace;font-size:20px;font-weight:700;
                         color:#c9a227;letter-spacing:2px;">{password}</td>
            </tr>
          </table>
        </div>
        <p style="color:#ef4444;font-size:13px;font-weight:600;">
          ⚠️ Change your password after first login.
        </p>
    """, f"Your Login — {role}")
    return _send(to_email, f"🔐 Your SapthaEvent Login — {role}", html)


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> bool:
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name or 'User'}</strong>,</p>
        <p style="color:#475569;">We received a request to reset your
           SapthaEvent password. Click the button below to set a new one.
           This link expires in <strong>1 hour</strong>.</p>
        <p style="text-align:center;margin:24px 0;">
          <a href="{reset_url}"
             style="background:#1a2557;color:#fff;padding:12px 32px;
                    border-radius:8px;text-decoration:none;font-weight:700;
                    display:inline-block;">
            Reset My Password →
          </a>
        </p>
        <p style="color:#64748b;font-size:12px;">
          If the button doesn't work, copy this link into your browser:<br>
          <span style="word-break:break-all;color:#1a2557;">{reset_url}</span>
        </p>
        <p style="color:#ef4444;font-size:12px;margin-top:18px;">
          Didn't request this? You can safely ignore this email — your
          password will remain unchanged.
        </p>
    """, "Password Reset Request")
    return _send(to_email, "🔐 Reset your SapthaEvent password", html)


def send_appointment_email(to_email: str, name: str, role: str,
                           event_title: str) -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#1a2557;">{role}</strong>
           for <strong>{event_title}</strong>.</p>
        <p style="margin-top:20px;">
          <a href="{base}/login"
             style="background:#c9a227;color:#fff;padding:10px 24px;
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
          <p style="color:#1a2557;font-weight:700;font-size:16px;margin:0;">
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
                    f"<strong style='color:#1a2557;'>Score: {score}</strong>")
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


def send_room_assignment_email(to_email: str, name: str, event_title: str,
                               room_name: str, event_date: str = '',
                               event_time: str = '', venue: str = '') -> bool:
    details = ''
    if event_date:
        details += (f"<tr><td style='color:#64748b;padding:6px 0;width:30%;'>Date</td>"
                    f"<td style='font-weight:600;color:#1a2557;'>📅 {event_date}</td></tr>")
    if event_time:
        details += (f"<tr><td style='color:#64748b;padding:6px 0;'>Time</td>"
                    f"<td style='font-weight:600;color:#1a2557;'>🕐 {event_time}</td></tr>")
    if venue:
        details += (f"<tr><td style='color:#64748b;padding:6px 0;'>Venue</td>"
                    f"<td style='font-weight:600;color:#1a2557;'>📍 {venue}</td></tr>")
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">Your room assignment for
           <strong style="color:#1a2557;">{event_title}</strong> is confirmed.</p>
        <div style="background:#f0fdf4;border:2px solid #86efac;border-radius:12px;
                    padding:24px;text-align:center;margin:16px 0;">
          <p style="color:#64748b;font-size:12px;margin:0 0 8px;font-weight:700;
                    text-transform:uppercase;letter-spacing:.5px;">Your Assigned Room</p>
          <p style="font-family:monospace;font-size:34px;font-weight:800;
                    color:#15803d;margin:0;">{room_name}</p>
        </div>
        <div style="background:#f8fafc;border-radius:10px;padding:16px;margin:16px 0;">
          <table style="width:100%;font-size:14px;border-collapse:collapse;">{details}</table>
        </div>
        <p style="color:#475569;font-size:13px;">
          Please report directly to your assigned room on the event day.
          Carry your QR ticket for check-in at the room entrance.
        </p>
    """, f"Room Assignment — {event_title}")
    return _send(to_email, f"🏛️ Your Room: {room_name} — {event_title}", html)


def send_advancement_email(to_email: str, name: str, event_title: str,
                           next_round: int, room_name: str = '',
                           event_time: str = '') -> bool:
    room_block = ''
    if room_name:
        room_block = f"""
        <div style="background:#eff6ff;border:1px solid #93c5fd;border-radius:10px;
                    padding:16px;margin:12px 0;text-align:center;">
          <p style="color:#1d4ed8;font-size:11px;margin:0 0 6px;font-weight:700;
                    text-transform:uppercase;letter-spacing:.5px;">Round {next_round} Room</p>
          <p style="font-family:monospace;font-size:26px;font-weight:800;
                    color:#1a2557;margin:0;">{room_name}</p>
        </div>"""
    time_note = (f"<p style='color:#475569;font-size:13px;'>Report time: "
                 f"<strong>{event_time}</strong></p>") if event_time else ''
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <div style="background:#f0fdf4;border:2px solid #86efac;border-radius:12px;
                    padding:20px;text-align:center;margin:16px 0;">
          <p style="font-size:30px;margin:0 0 8px;">🎉</p>
          <p style="color:#15803d;font-weight:800;font-size:18px;margin:0 0 6px;">Congratulations!</p>
          <p style="color:#475569;margin:0;">You have advanced to
             <strong>Round {next_round}</strong> of
             <strong style="color:#1a2557;">{event_title}</strong>!</p>
        </div>
        {room_block}
        {time_note}
        <p style="color:#475569;font-size:13px;">Keep up the great work — best of luck in the next round!</p>
    """, f"Round {next_round} Advancement — {event_title}")
    return _send(to_email, f"🎉 You advanced to Round {next_round}! — {event_title}", html)


# Alias used by utils_certificate.py
def _get_mail():
    return None