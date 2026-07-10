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
from utils_email import _send_cert_email, LAST_EMAIL_ERROR

def send_test():
    target_email = "biradark56@gmail.com"
    name = "Kiran Biradar"
    event_title = "Global AI Hackathon 2026"
    
    print("Initializing Flask context...")
    with app.app_context():
        # Set base URLs
        os.environ['BASE_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app"
        os.environ['COLLEGE_LOGO_URL'] = "https://saptha-event-portal-762269836348.us-east4.run.app/static/snpsu-logo.png"

        print("\nGenerating upgraded Winner Certificate PDF...")
        try:
            winner_pdf = generate_certificate_pdf(
                student_name=name,
                event_title=event_title,
                reg_id="CERT-WIN-MIND-BLOWING",
                cert_type="winner",
                rank=1,
                score=99.5,
                event_date="Jun 10, 2026",
                base_url="https://saptha-event-portal-762269836348.us-east4.run.app",
                college_name="Sapthagiri NPS University"
            )
            
            # Save a local copy for manual review/reference
            local_pdf_path = os.path.join(os.path.dirname(__file__), "mind_blowing_certificate.pdf")
            with open(local_pdf_path, "wb") as f:
                f.write(winner_pdf)
            print(f"Saved local certificate preview to: {local_pdf_path}")
            
            print(f"\nSending Winner Certificate to {target_email}...")
            ok = _send_cert_email(
                to_email=target_email,
                student_name=name,
                event_title=event_title,
                cert_type="winner",
                rank=1,
                score=99.5,
                pdf_bytes=winner_pdf,
                reg_id="CERT-WIN-MIND-BLOWING"
            )
            if ok:
                print("SUCCESS: Certificate email sent successfully!")
            else:
                print(f"FAILED: Email delivery failed. Error: {LAST_EMAIL_ERROR}")
        except Exception as e:
            print(f"Error during certificate generation/sending: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    send_test()
