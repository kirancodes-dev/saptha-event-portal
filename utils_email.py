"""
utils_email.py — SapthaEvent Email via Resend API

WHY RESEND: Railway blocks SMTP ports (587/465). Resend uses HTTPS (port 443)
which Railway allows. Free tier: 100 emails/day, 3000/month.

SETUP (5 minutes):
  1. Go to resend.com → sign up free
  2. Dashboard → API Keys → Create API Key → copy it
  3. In Railway Variables add:
       RESEND_API_KEY = re_xxxxxxxxxxxxxxxxxxxx
       MAIL_FROM      = SapthaEvent <onboarding@resend.dev>

  NOTE: On Resend free tier, you can only send FROM onboarding@resend.dev
  until you verify your own domain. That's fine for testing.
  To send from sapthhack@gmail.com you need to verify your domain at resend.com/domains

REQUIREMENTS: Add to requirements.txt:
  resend
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Resend client (lazy init) ────────────────────────────────
_resend_ready = False

def _init_resend() -> bool:
    global _resend_ready
    if _resend_ready:
        return True
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        logger.error("RESEND_API_KEY not set in Railway Variables. "
                     "Go to resend.com, get a free API key, "
                     "add RESEND_API_KEY to Railway Variables.")
        return False
    try:
        import resend
        resend.api_key = api_key
        _resend_ready  = True
        return True
    except ImportError:
        logger.error("resend package not installed. Add 'resend' to requirements.txt")
        return False


def _from_address() -> str:
    return os.environ.get(
        'MAIL_FROM',
        'SapthaEvent <onboarding@resend.dev>'
    )


def _base_url() -> str:
    try:
        from flask import current_app
        return current_app.config.get('BASE_URL',
               'https://saptha-event-portal-production.up.railway.app')
    except Exception:
        return os.environ.get('BASE_URL',
               'https://saptha-event-portal-production.up.railway.app')


def _html_wrapper(content: str, title: str = 'SapthaEvent') -> str:
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


def _send(to_email, subject: str, html: str,
          attachments: list = None) -> bool:
    """
    Core send via Resend API (HTTPS — works on Railway).
    Never raises. Returns True on success, False on failure.
    attachments = [{'filename': 'cert.pdf', 'content': base64_string}]
    """
    if not _init_resend():
        return False
    try:
        import resend
        to_list = [to_email] if isinstance(to_email, str) else to_email

        params = {
            'from':    _from_address(),
            'to':      to_list,
            'subject': subject,
            'html':    html,
        }
        if attachments:
            params['attachments'] = attachments

        resend.Emails.send(params)
        logger.info("Email sent via Resend to %s — %s", to_list, subject)
        return True
    except Exception as exc:
        logger.error("Resend email failed to %s: %s", to_email, exc)
        return False


# ── Public email functions ────────────────────────────────────

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
            Your Ticket ID
          </p>
          <p style="font-family:monospace;font-size:22px;color:#0d2d62;
                    font-weight:700;margin:0;">{reg_id}</p>
        </div>
        <p style="color:#475569;font-size:13px;">
          Show your Ticket ID at the venue for check-in.
          {'Your QR code is attached.' if qr_bytes else ''}
        </p>
        <p style="margin-top:20px;">
          <a href="{base}/participant/dashboard"
             style="background:#0d2d62;color:#fff;padding:10px 24px;border-radius:8px;
                    text-decoration:none;font-weight:700;font-size:14px;">
            View My Dashboard →
          </a>
        </p>
    """, f"Registration Confirmed — {event_title}")

    attachments = []
    if qr_bytes:
        import base64
        attachments.append({
            'filename': 'QR_Ticket.png',
            'content':  base64.b64encode(qr_bytes).decode(),
        })

    return _send(to_email,
                 f"✅ Registration Confirmed — {event_title}",
                 html,
                 attachments or None)


def send_credentials_email(to_email: str, name: str, role: str,
                           password: str, category: str = '') -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong>
           {f'for <strong>{category}</strong> events' if category else ''}
           on the SapthaEvent Portal.</p>
        <div style="background:#e8f0fe;border-radius:10px;padding:20px;margin:16px 0;">
          <table style="width:100%;font-size:14px;border-collapse:collapse;">
            <tr>
              <td style="color:#64748b;padding:8px 0;width:35%;">Login URL</td>
              <td style="font-weight:700;">
                <a href="{base}/login" style="color:#0d2d62;">{base}/login</a>
              </td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Email</td>
              <td style="font-weight:700;color:#0d2d62;">{to_email}</td>
            </tr>
            <tr>
              <td style="color:#64748b;padding:8px 0;">Password</td>
              <td style="font-family:monospace;font-size:18px;font-weight:700;
                         color:#f37021;letter-spacing:2px;">{password}</td>
            </tr>
          </table>
        </div>
        <p style="color:#ef4444;font-size:13px;font-weight:600;">
          ⚠️ Please change your password after your first login.
        </p>
    """, f"Your Login — {role} at SapthaEvent")

    return _send(to_email, f"🔐 Your SapthaEvent Login — {role}", html)


def send_appointment_email(to_email: str, name: str, role: str,
                           event_title: str) -> bool:
    base = _base_url()
    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;">You have been appointed as
           <strong style="color:#0d2d62;">{role}</strong> for
           <strong>{event_title}</strong>.</p>
        <p style="margin-top:20px;">
          <a href="{base}/login"
             style="background:#f37021;color:#fff;padding:10px 24px;border-radius:8px;
                    text-decoration:none;font-weight:700;font-size:14px;">
            Login to Dashboard →
          </a>
        </p>
    """, f"Appointment — {event_title}")

    return _send(to_email, f"📋 You've been appointed — {event_title}", html)


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
            Final Score: {score}
          </p>
        </div>
        <p style="color:#475569;">Congratulations on your achievement in
           <strong>{event_title}</strong>!</p>
        <p style="color:#475569;font-size:13px;">
          Your certificate has been emailed separately — check your inbox!
        </p>
    """, f"🏆 Results — {event_title}")

    return _send(to_email, f"🏆 Results Published — {event_title}", html)


def send_broadcast_email(to_list: list, subject: str,
                         message: str, event_title: str = '') -> bool:
    html = _html_wrapper(f"""
        <div style="color:#475569;font-size:14px;line-height:1.8;white-space:pre-line;">
          {message}
        </div>
    """, subject)

    success = True
    # Send individually to avoid spam filters
    for email in to_list:
        if email:
            ok = _send(email, subject, html)
            if not ok:
                success = False
    return success


def send_certificate_email(to_email: str, student_name: str,
                           event_title: str, cert_type: str,
                           rank: int, score: float,
                           pdf_bytes: bytes) -> bool:
    """Send certificate PDF as attachment via Resend."""
    import base64

    rank_labels = {1: '🥇 1st Place', 2: '🥈 2nd Place', 3: '🥉 3rd Place'}

    if cert_type == 'winner':
        subject  = f"🏆 Your Achievement Certificate — {event_title}"
        headline = f"Congratulations! You achieved {rank_labels.get(rank, f'Rank {rank}')}"
        body     = (f"Your <strong>Certificate of Achievement</strong> for "
                    f"<strong>{event_title}</strong> is attached.<br><br>"
                    f"<strong style='color:#0d2d62;font-size:16px;'>Final Score: {score}</strong>")
    else:
        subject  = f"🎓 Your Participation Certificate — {event_title}"
        headline = f"Thank you for participating in {event_title}!"
        body     = (f"Your <strong>Certificate of Participation</strong> for "
                    f"<strong>{event_title}</strong> is attached.")

    html = _html_wrapper(f"""
        <p style="color:#475569;">Dear <strong>{student_name}</strong>,</p>
        <p style="color:#475569;">{body}</p>
        <div style="background:#f8fafc;border-radius:10px;padding:16px;
                    margin:16px 0;font-size:13px;color:#475569;">
          <strong>What to do with your certificate:</strong>
          <ul style="margin:8px 0 0;padding-left:20px;line-height:2.2;">
            <li>Download and save the attached PDF</li>
            <li>Share it on <strong>LinkedIn</strong></li>
            <li>Scan the QR code to verify authenticity</li>
          </ul>
        </div>
    """, headline)

    safe_title = event_title.replace(' ', '_').replace('/', '_')[:35]
    cert_label = 'Achievement' if cert_type == 'winner' else 'Participation'

    attachments = [{
        'filename': f"Certificate_{cert_label}_{safe_title}.pdf",
        'content':  base64.b64encode(pdf_bytes).decode(),
    }]

    return _send(to_email, subject, html, attachments)


# ── Kept for backwards compatibility with utils_certificate.py ──
def _get_mail():
    """Legacy stub — Resend doesn't use Flask-Mail."""
    return None