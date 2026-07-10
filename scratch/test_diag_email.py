import os
import sys
sys.path.insert(0, '/Users/kiranbiradar/Desktop/saptha-event-portal')

# Load env variables from .env
from dotenv import load_dotenv
load_dotenv()

import utils_email

print("BREVO_API_KEY:", bool(os.environ.get('BREVO_API_KEY')))
print("RESEND_API_KEY:", bool(os.environ.get('RESEND_API_KEY')))
print("MAIL_USER:", os.environ.get('MAIL_USER'))
print("MAIL_PASS:", bool(os.environ.get('MAIL_PASS')))

to_email = "biradark543@gmail.com"
print(f"Sending test email to {to_email}...")
success = utils_email._send(to_email, "SapthaEvent — Local Diagnostic", "<p>Testing local email delivery. If you see this, it works!</p>")
print("Success:", success)
print("LAST_EMAIL_ERROR:", utils_email.LAST_EMAIL_ERROR)
