from flask_mail import Message
from flask import current_app
import logging
import io
import qrcode
from qrcode.image.pil import PilImage

logger = logging.getLogger(__name__)


def _get_mail():
    mail = current_app.extensions.get('mail')
    if mail is None:
        raise RuntimeError("Flask-Mail is not initialised on the app.")
    return mail


def _send(msg) -> bool:
    try:
        _get_mail().send(msg)
        return True
    except Exception as exc:
        logger.error("Email send failed to %s — %s", msg.recipients, exc)
        return False


def _base_url() -> str:
    try:
        return current_app.config.get('BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    except Exception:
        return 'http://127.0.0.1:5000'


def _generate_qr_bytes(data: str) -> bytes:
    """Generate QR code and return raw PNG bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# =========================================================
# 1. CREDENTIALS EMAIL
# =========================================================
def send_credentials_email(to_email, name, role, password, category="General"):
    msg = Message(
        subject=f"Welcome to SapthaEvent — Your {role} Login Credentials",
        recipients=[to_email]
    )
    msg.html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:24px;
                border:1px solid #e2e8f0;border-radius:8px;">
      <h2 style="color:#0d2d62;">Welcome to SapthaEvent, {name}!</h2>
      <p>You have been registered as <strong>{role}</strong> for the <strong>{category}</strong> division.</p>
      <table style="border-collapse:collapse;width:100%;margin:16px 0;">
        <tr style="background:#f7fafc;">
          <td style="padding:10px;border:1px solid #e2e8f0;font-weight:bold;">Role</td>
          <td style="padding:10px;border:1px solid #e2e8f0;">{role}</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #e2e8f0;font-weight:bold;">Login Email</td>
          <td style="padding:10px;border:1px solid #e2e8f0;">{to_email}</td>
        </tr>
        <tr style="background:#f7fafc;">
          <td style="padding:10px;border:1px solid #e2e8f0;font-weight:bold;">Temporary Password</td>
          <td style="padding:10px;border:1px solid #e2e8f0;
                     font-family:monospace;font-size:16px;color:#e53e3e;">{password}</td>
        </tr>
      </table>
      <p style="color:#e53e3e;"><strong>⚠️ You will be forced to change this password on first login.</strong></p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
      <p style="color:#a0aec0;font-size:12px;">SapthaEvent — Sapthagiri NPS University</p>
    </div>"""
    msg.body = (f"Hello {name},\n\nYou are registered as {role} for {category}.\n\n"
                f"Email: {to_email}\nTemporary Password: {password}\n\n"
                f"Change your password on first login.\n\nRegards,\nSapthaEvent Admin")
    return _send(msg)


# =========================================================
# 2. APPOINTMENT EMAIL
# =========================================================
def send_appointment_email(to_email, name, role, event_title):
    msg = Message(
        subject=f"Event Appointment: {role} for {event_title}",
        recipients=[to_email]
    )
    msg.body = (f"Hello {name},\n\nYou have been appointed as {role} for '{event_title}'.\n\n"
                f"Log in using your existing credentials to access your new {role} dashboard.\n\n"
                f"Regards,\nSapthaEvent Coordinators")
    return _send(msg)


# =========================================================
# 3. TICKET EMAIL
# QR is sent as a regular PNG attachment.
# Works 100% on localhost — no hosting or CID tricks needed.
# Participant opens the attachment to scan their QR.
# =========================================================
def send_ticket_email(to_email: str, name: str, event_title: str,
                      reg_id: str, is_new_user: bool = False,
                      raw_password: str = "") -> bool:

    base_url   = _base_url()
    ticket_url = f"{base_url}/ticket/{reg_id}"

    # Generate QR for the ticket ID
    try:
        qr_bytes = _generate_qr_bytes(reg_id)
        has_qr   = True
    except Exception as exc:
        logger.warning("QR generation failed: %s", exc)
        qr_bytes = None
        has_qr   = False

    new_user_html = ""
    new_user_text = ""
    if is_new_user and raw_password:
        new_user_html = f"""
        <div style="background:#fffbeb;border:1px solid #fbbf24;border-radius:8px;
                    padding:16px;margin:16px 0;">
          <p style="margin:0 0 8px;font-weight:700;color:#92400e;">🎉 Your portal account was created!</p>
          <table style="font-size:14px;">
            <tr><td style="color:#78716c;padding:2px 8px 2px 0;">Login Email</td>
                <td style="font-family:monospace;">{to_email}</td></tr>
            <tr><td style="color:#78716c;padding:2px 8px 2px 0;">Password</td>
                <td style="font-family:monospace;color:#dc2626;font-weight:700;">{raw_password}</td></tr>
          </table>
          <p style="margin:8px 0 0;font-size:12px;color:#a16207;">
            You will be asked to change this on first login.
          </p>
        </div>"""
        new_user_text = (f"\n--- YOUR NEW PORTAL ACCOUNT ---\n"
                         f"Login Email: {to_email}\n"
                         f"Temporary Password: {raw_password}\n"
                         f"(Change this on first login)\n")

    qr_note = ""
    if has_qr:
        qr_note = """
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;
                    padding:12px 16px;margin:16px 0;text-align:center;">
          <p style="margin:0;color:#166534;font-size:13px;">
            📎 <strong>Your QR code is attached</strong> to this email as
            <code>QR_Ticket.png</code><br>
            Open the attachment and show it at the venue entrance.
          </p>
        </div>"""

    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:auto;
                background:#ffffff;border-radius:12px;overflow:hidden;
                border:1px solid #e2e8f0;">

      <div style="background:#0d2d62;padding:28px 28px 20px;text-align:center;">
        <p style="color:rgba(255,255,255,0.7);font-size:11px;letter-spacing:2px;
                  text-transform:uppercase;margin:0 0 6px;">Sapthagiri NPS University</p>
        <h1 style="color:white;font-size:20px;margin:0;">🎟️ Registration Confirmed!</h1>
      </div>

      <div style="padding:24px 28px;">
        <p style="font-size:16px;color:#1e293b;">Hello <strong>{name}</strong>,</p>
        <p style="color:#475569;">You are registered for <strong>{event_title}</strong>.</p>

        <div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;
                    margin:16px 0;text-align:center;">
          <p style="margin:0;font-size:11px;color:#94a3b8;letter-spacing:1px;
                    text-transform:uppercase;">Ticket ID</p>
          <p style="margin:6px 0 0;font-family:monospace;font-size:22px;
                    font-weight:700;color:#0d2d62;">{reg_id}</p>
        </div>

        {qr_note}
        {new_user_html}

        <p style="color:#64748b;font-size:13px;margin-top:20px;">
          View your ticket anytime at:<br>
          <a href="{ticket_url}" style="color:#1a4fa0;">{ticket_url}</a>
        </p>
      </div>

      <div style="background:#f8fafc;padding:14px 28px;text-align:center;
                  border-top:1px solid #e2e8f0;">
        <p style="margin:0;font-size:11px;color:#94a3b8;">
          SapthaEvent · Sapthagiri NPS University
        </p>
      </div>
    </div>"""

    msg      = Message(subject=f"Your Ticket: {event_title}", recipients=[to_email])
    msg.html = html_body
    msg.body = (f"Hello {name},\n\nYour registration for '{event_title}' is confirmed!\n"
                f"Ticket ID: {reg_id}\n"
                f"View ticket: {ticket_url}\n"
                f"{new_user_text}\n"
                f"Your QR code is attached as QR_Ticket.png — show it at the venue.\n\n"
                f"Regards,\nSapthaEvent")

    # Attach QR as a regular downloadable PNG attachment
    # Simple, reliable, works in Gmail on localhost with no hosting needed
    if has_qr and qr_bytes:
        msg.attach(
            filename='QR_Ticket.png',
            content_type='image/png',
            data=qr_bytes
        )

    return _send(msg)


# =========================================================
# 4. BROADCAST EMAIL
# =========================================================
def send_broadcast_email(email_list, subject, message, event_title):
    if not email_list:
        return False
    try:
        mail = _get_mail()
        with mail.connect() as conn:
            for email in email_list:
                msg = Message(
                    subject=f"[{event_title}] {subject}",
                    recipients=[email]
                )
                msg.body = (f"Important update regarding {event_title}:\n\n"
                            f"{message}\n\nRegards,\nEvent Organizers")
                conn.send(msg)
        return True
    except Exception as exc:
        logger.error("Broadcast email error: %s", exc)
        return False


# =========================================================
# 5. RESULT ANNOUNCEMENT EMAIL
# =========================================================
def send_result_email(to_email, name, event_title, rank, score):
    base_url    = _base_url()
    rank_labels = {1: "🥇 1st Place", 2: "🥈 2nd Place", 3: "🥉 3rd Place"}
    rank_text   = rank_labels.get(rank, f"Top {rank}")
    msg = Message(subject=f"Results Published: {event_title}", recipients=[to_email])
    msg.html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:24px;
                border:1px solid #e2e8f0;border-radius:8px;text-align:center;">
      <h2 style="color:#0d2d62;">🏆 Results Are In!</h2>
      <p>Hello <strong>{name}</strong>,</p>
      <p>Results for <strong>{event_title}</strong> are published.</p>
      <div style="background:#f0fff4;border:1px solid #68d391;border-radius:8px;
                  padding:20px;margin:16px auto;display:inline-block;">
        <p style="font-size:22px;margin:0;">{rank_text}</p>
        <p style="color:#2d3748;margin:6px 0 0;">Final Score: <strong>{score}</strong></p>
      </div>
      <p>Log in to view the full leaderboard and download your certificate.</p>
      <a href="{base_url}/participant/dashboard"
         style="display:inline-block;background:#0d2d62;color:white;
                padding:12px 28px;border-radius:8px;text-decoration:none;
                font-weight:bold;margin:8px 0;">View Leaderboard</a>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
      <p style="color:#a0aec0;font-size:12px;">SapthaEvent — Sapthagiri NPS University</p>
    </div>"""
    msg.body = (f"Hello {name},\n\nResults for '{event_title}' are published.\n"
                f"Your result: {rank_text} — Score: {score}\n\n"
                f"Log in to the portal to see the full leaderboard.\n\nRegards,\nSapthaEvent")
    return _send(msg)