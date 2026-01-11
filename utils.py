import smtplib, ssl, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
SMTP_EMAIL = "sapthhack@gmail.com"  # Update this
SMTP_PASSWORD = "bbcw iimk ghvu pvof" # Update this
otp_storage = {}

def generate_otp():
    return str(random.randint(100000, 999999))

def send_email(to_email, subject, body_html):
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- NEW: AI ANALYSIS ENGINE ---
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