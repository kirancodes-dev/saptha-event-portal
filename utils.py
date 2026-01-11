import smtplib, ssl, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import db # Import Firebase DB

# --- CONFIGURATION ---
SMTP_EMAIL = "sapthhack@gmail.com"  
SMTP_PASSWORD = "bbcw iimk ghvu pvof" 

def generate_otp(email):
    """Generates a 6-digit OTP and saves it to Firestore."""
    otp = str(random.randint(100000, 999999))
    
    # Save to Firebase (Collection: 'otps')
    # This ensures OTPs survive if the server restarts
    try:
        db.collection('otps').document(email).set({
            'otp': otp
        })
    except Exception as e:
        print(f"Error saving OTP to DB: {e}")
        
    return otp

def verify_otp_logic(email, user_input):
    """Helper to verify OTP from Firestore"""
    try:
        doc = db.collection('otps').document(email).get()
        if doc.exists:
            stored_otp = doc.to_dict().get('otp')
            if str(stored_otp) == str(user_input):
                # Optional: Delete OTP after successful use
                db.collection('otps').document(email).delete()
                return True
    except Exception as e:
        print(f"OTP Verify Error: {e}")
    return False

def send_email(to_email, subject, body_html):
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls(context=context)
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- AI ANALYSIS ENGINE ---
def ai_analyze_domain(text):
    """
    Scans the problem statement and returns detected Tech Stacks.
    """
    if not text: return "General"
    text = text.lower()
    tags = []
    
    keywords = {
        "AI/ML": ["ai", "machine learning", "neural", "predict", "model", "vision"],
        "Blockchain": ["crypto", "chain", "web3", "decentralized", "token"],
        "IoT": ["sensor", "arduino", "hardware", "device", "robot", "drone"],
        "Web/App": ["website", "app", "platform", "portal", "react", "node"],
        "Cloud": ["aws", "azure", "cloud", "server", "deploy"],
        "Cybersec": ["security", "hack", "encrypt", "privacy"]
    }
    
    for domain, keys in keywords.items():
        if any(k in text for k in keys):
            tags.append(domain)
            
    if not tags: return "Innovation"
    return ", ".join(tags)