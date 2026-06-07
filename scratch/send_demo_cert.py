import os
import sys

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)

from app import app
from utils_certificate import generate_certificate_pdf
from utils_email import _send_cert_email

def send_demo():
    print("Initializing Flask context...")
    with app.app_context():
        to_email = "biradark56@gmail.com"
        student_name = "Kiran Biradar"
        event_title = "Build with AI Bangalore"
        cert_type = "winner"
        rank = 1
        score = 98.5
        reg_id = "2026H2S05BWAIBLR-P00273"
        event_date = "Jun 4, 2026"
        
        print("Generating certificate PDF...")
        try:
            pdf_bytes = generate_certificate_pdf(
                student_name=student_name,
                event_title=event_title,
                reg_id=reg_id,
                cert_type=cert_type,
                rank=rank,
                score=score,
                event_date=event_date,
                base_url="https://saptha-event-portal-762269836348.us-east4.run.app",
                college_name="Sapthagiri NPS University"
            )
            print("PDF Certificate generated successfully.")
        except Exception as e:
            print(f"Error generating PDF certificate: {e}")
            return

        print(f"Sending demo email to {to_email}...")
        try:
            # We override BASE_URL to the production domain for the email links
            os.environ['BASE_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app"
            os.environ['COLLEGE_LOGO_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app/static/snpsu-logo.png"
            
            success = _send_cert_email(
                to_email=to_email,
                student_name=student_name,
                event_title=event_title,
                cert_type=cert_type,
                rank=rank,
                score=score,
                pdf_bytes=pdf_bytes,
                reg_id=reg_id
            )
            if success:
                print("SUCCESS: Demo email with certificate attachment was successfully sent!")
            else:
                from utils_email import LAST_EMAIL_ERROR
                print(f"FAILED: Email sending failed. Error: {LAST_EMAIL_ERROR}")
        except Exception as e:
            print(f"Error sending email: {e}")

if __name__ == "__main__":
    send_demo()
