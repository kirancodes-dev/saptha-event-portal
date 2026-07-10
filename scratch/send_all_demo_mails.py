import os
import sys
import io
import qrcode
import base64

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)

from app import app
from utils_certificate import generate_certificate_pdf
from utils_email import (
    send_registration_confirmed_email,
    send_ticket_email,
    send_credentials_email,
    send_password_reset_email,
    send_appointment_email,
    send_result_email,
    _send_cert_email,
    send_room_assignment_email,
    send_advancement_email,
    LAST_EMAIL_ERROR
)

def send_all_demos():
    target_email = "biradark543@gmail.com"
    name = "Kiran Biradar"
    event_title = "Global AI Hackathon 2026"
    event_date = "June 15, 2026"
    venue = "Main Auditorium, SNPSU Campus"
    
    print("Initializing Flask context...")
    with app.app_context():
        # Set base URLs
        os.environ['BASE_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app"
        os.environ['COLLEGE_LOGO_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app/static/snpsu-logo.png"

        # 1. Registration Confirmed Email
        print("\n1. Sending Registration Confirmed Email...")
        ok = send_registration_confirmed_email(
            to_email=target_email,
            name=name,
            event_title=event_title,
            event_date=event_date,
            venue=venue,
            is_new_user=True,
            raw_password="TempPassword123!"
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 2. Ticket Email (with QR Code)
        print("\n2. Sending Ticket Email with QR Code...")
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data("https://saptha-event-portal-762269836348.us-east4.run.app/verify/SNPSU-HACK-7890")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_bytes = buf.getvalue()

        ok = send_ticket_email(
            to_email=target_email,
            name=name,
            event_title=event_title,
            reg_id="SNPSU-HACK-7890",
            qr_bytes=qr_bytes,
            is_new_user=False,
            raw_password=None
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 3. Credentials Email
        print("\n3. Sending Credentials Email...")
        ok = send_credentials_email(
            to_email=target_email,
            name=name,
            role="Judge",
            password="SecureJudgePass99!",
            category="Technical"
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 4. Password Reset Email
        print("\n4. Sending Password Reset Email...")
        ok = send_password_reset_email(
            to_email=target_email,
            name=name,
            reset_url="https://saptha-event-portal-762269836348.us-east4.run.app/reset/abc123xyz"
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 5. Appointment Email
        print("\n5. Sending Appointment Email...")
        ok = send_appointment_email(
            to_email=target_email,
            name=name,
            role="Event SPOC",
            event_title="Cultural Fest 2026"
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 6. Result Email
        print("\n6. Sending Result Email...")
        ok = send_result_email(
            to_email=target_email,
            name=name,
            event_title="Coding Arena 2026",
            rank=1,
            score=95.0
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 7. Winner Certificate Email
        print("\n7. Generating and sending Winner Certificate Email...")
        try:
            winner_pdf = generate_certificate_pdf(
                student_name=name,
                event_title="Coding Arena 2026",
                reg_id="CERT-WIN-001",
                cert_type="winner",
                rank=1,
                score=95.0,
                event_date="Jun 10, 2026",
                base_url="https://saptha-event-portal-762269836348.us-east4.run.app",
                college_name="Sapthagiri NPS University"
            )
            ok = _send_cert_email(
                to_email=target_email,
                student_name=name,
                event_title="Coding Arena 2026",
                cert_type="winner",
                rank=1,
                score=95.0,
                pdf_bytes=winner_pdf,
                reg_id="CERT-WIN-001"
            )
            print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")
        except Exception as e:
            print(f"Error sending Winner Certificate: {e}")

        # 8. Participation Certificate Email
        print("\n8. Generating and sending Participation Certificate Email...")
        try:
            part_pdf = generate_certificate_pdf(
                student_name=name,
                event_title="Coding Arena 2026",
                reg_id="CERT-PART-002",
                cert_type="participation",
                rank=0,
                score=0.0,
                event_date="Jun 10, 2026",
                base_url="https://saptha-event-portal-762269836348.us-east4.run.app",
                college_name="Sapthagiri NPS University"
            )
            ok = _send_cert_email(
                to_email=target_email,
                student_name=name,
                event_title="Coding Arena 2026",
                cert_type="participation",
                rank=0,
                score=0.0,
                pdf_bytes=part_pdf,
                reg_id="CERT-PART-002"
            )
            print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")
        except Exception as e:
            print(f"Error sending Participation Certificate: {e}")

        # 9. Room Assignment Email
        print("\n9. Sending Room Assignment Email...")
        ok = send_room_assignment_email(
            to_email=target_email,
            name=name,
            event_title=event_title,
            room_name="Lab 305 (Suryodaya Block)",
            event_date=event_date,
            event_time="09:30 AM",
            venue=venue
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

        # 10. Advancement Email
        print("\n10. Sending Advancement Email...")
        ok = send_advancement_email(
            to_email=target_email,
            name=name,
            event_title=event_title,
            next_round=2,
            room_name="Seminar Hall A (Main Block)",
            event_time="02:00 PM"
        )
        print(f"Status: {'SUCCESS' if ok else 'FAILED (' + LAST_EMAIL_ERROR + ')'}")

if __name__ == "__main__":
    send_all_demos()
