from flask_mail import Message
from flask import current_app
import logging

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
# 3. TICKET EMAIL  ← QR EMBEDDED HERE
# =========================================================
def send_ticket_email(to_email: str, name: str, event_title: str,
                      reg_id: str, is_new_user: bool = False,
                      raw_password: str = "",
                      base_url: str = "https://your-app.onrender.com") -> bool:
    try:
        from utils_qr import generate_qr_base64
        verify_url = f"{base_url}/ticket/verify/{reg_id}"
        qr_b64     = generate_qr_base64(verify_url, box_size=6)
    except Exception as exc:
        logger.warning("QR generation failed, sending email without QR: %s", exc)
        qr_b64 = None

    msg = Message(
        subject=f"Your Ticket: {event_title}",
        recipients=[to_email]
    )

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

    qr_block = ""
    if qr_b64:
        qr_block = f"""
        <div style="text-align:center;margin:20px 0;">
          <p style="font-size:12px;color:#94a3b8;margin:0 0 10px;">
            Show this QR at the venue entrance
          </p>
          <img src="data:image/png;base64,{qr_b64}"
               width="180" height="180" alt="Entry QR Code"
               style="border:2px solid #e2e8f0;border-radius:12px;padding:8px;">
          <p style="font-size:11px;color:#cbd5e1;margin:8px 0 0;">
            Or show your Ticket ID: <code>{reg_id}</code>
          </p>
        </div>"""

    msg.html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:auto;
                background:#ffffff;border-radius:12px;overflow:hidden;
                border:1px solid #e2e8f0;">
      <div style="background:linear-gradient(135deg,#0d2d62,#1a4fa0);
                  padding:28px 28px 20px;text-align:center;">
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
          <p style="margin:6px 0 0;font-family:monospace;font-size:20px;
                    font-weight:700;color:#0d2d62;">{reg_id}</p>
        </div>
        {qr_block}
        {new_user_html}
        <p style="color:#64748b;font-size:13px;">
          View your ticket anytime at:<br>
          <a href="{base_url}/ticket/{reg_id}" style="color:#1a4fa0;">
            {base_url}/ticket/{reg_id}
          </a>
        </p>
      </div>
      <div style="background:#f8fafc;padding:14px 28px;text-align:center;
                  border-top:1px solid #e2e8f0;">
        <p style="margin:0;font-size:11px;color:#94a3b8;">
          SapthaEvent · Sapthagiri NPS University
        </p>
      </div>
    </div>"""

    msg.body = (f"Hello {name},\n\nYour registration for '{event_title}' is confirmed!\n"
                f"Ticket ID: {reg_id}\n"
                f"View ticket: {base_url}/ticket/{reg_id}\n"
                f"{new_user_text}\n"
                f"Show your Ticket ID or QR code at the venue.\n\nRegards,\nSapthaEvent")
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
    rank_labels = {1: "🥇 1st Place", 2: "🥈 2nd Place", 3: "🥉 3rd Place"}
    rank_text   = rank_labels.get(rank, f"Top {rank}")
    msg = Message(
        subject=f"Results Published: {event_title}",
        recipients=[to_email]
    )
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
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
      <p style="color:#a0aec0;font-size:12px;">SapthaEvent — Sapthagiri NPS University</p>
    </div>"""
    msg.body = (f"Hello {name},\n\nResults for '{event_title}' are published.\n"
                f"Your result: {rank_text} — Score: {score}\n\n"
                f"Log in to the portal to see the full leaderboard.\n\nRegards,\nSapthaEvent")
    return _send(msg)