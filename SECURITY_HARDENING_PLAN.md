# Security Hardening & Threat Mitigation Plan

> **Scope:** Zero-Trust Architecture, Credential Sanitization, Anti-Replay & Compliance  
> **Status:** Phase 1 Deliverable — Security Engineering Plan  

---

## 1. Vulnerability Assessment & Priority Matrix

| Risk ID | Vulnerability | Current State in Repository | Severity | Remediation Strategy |
|---|---|---|---|---|
| **SEC-01** | **Public Credentials in Docs** | `README.md` (lines 536–540) exposes plaintext logins (`student@demo.com` / `Demo1234`). | **Critical** | Immediately purge demo credentials from documentation. Disable hardcoded default passwords in production. Force administrative password reset on first boot. |
| **SEC-02** | **Unauthenticated Self Check-in** | `/checkin/<event_id>/submit` accepts raw unauthenticated email in form POST. | **Critical** | Require cryptographic ticket token verification or authenticated student session with signed QR nonce. |
| **SEC-03** | **Insecure Direct Object Reference (IDOR)** | Endpoints like `/ticket/<reg_id>` and `/forms/responses/<event_id>` rely on UUIDs without checking ownership. | **High** | Implement object-level permission middleware: only the attendee, their team members, or authorized coordinators can access tickets and responses. |
| **SEC-04** | **Broad CSRF Exemptions** | `app.py` line 391 exempts entire blueprints from CSRF protection. | **Medium** | Transition JSON API endpoints to signed Authorization headers (`Bearer JWT` or custom session CSRF header `X-CSRF-Token`). |
| **SEC-05** | **Short JWT HMAC Secret Key** | Unit tests trigger `InsecureKeyLengthWarning` (key < 32 bytes for HS256). | **Medium** | Enforce cryptographically random 256-bit secrets via `secrets.token_hex(32)`. Reject boot if `JWT_SECRET_KEY` is under 32 bytes. |
| **SEC-06** | **Unrestricted File Upload Risks** | Dynamic form submissions allow file uploads with basic extension checks. | **High** | Validate MIME magic bytes via `python-magic`, enforce 10MB limit, sanitize filenames, and store outside webroot (or Cloud Storage bucket with private signed URLs). |
| **SEC-07** | **QR Replay & Ticket Counterfeiting** | QR codes encode static text / IDs without expiration or cryptographic signatures. | **High** | Implement time-stamped HMAC-SHA256 signed QR payloads with one-time redemption tracking. |

---

## 2. Hardening Strategy Details

### 2.1 Credential & Secret Management
1. **Purge Documentation:** Remove all password tables from `README.md` and user guides.
2. **Dynamic Seed Initialization:** Modify `seed_demo.py` to generate randomized secure passwords printed to stdout upon local dev initialization, rather than committing static credentials.
3. **Environment Isolation:** Ensure `serviceAccountKey.json`, `.env`, and private certs remain in `.gitignore`. Provide a clean `.env.example` template with placeholder values.

### 2.2 Object-Level Access Control (OLAC / IDOR Protection)
Implement a unified permission guard:
```python
def verify_registration_access(registration_dict, user_email, user_role):
    """Verify whether current user has legitimate access to this registration."""
    if user_role in ('SuperAdmin', 'Super Admin', 'Admin', 'Coordinator', 'ClubSPOC'):
        return True
    
    # Attendee themselves
    if registration_dict.get('lead_email', '').lower() == user_email.lower():
        return True
        
    # Team members
    for member in registration_dict.get('members', []):
        if member.get('email', '').lower() == user_email.lower():
            return True
            
    return False
```

### 2.3 Cryptographic Ticket Engine & Anti-Replay Tokens
Instead of embedding raw `registration_id` in QR codes:
```python
import hmac
import hashlib
import time

def generate_ticket_token(event_id: str, reg_id: str, secret_key: str) -> str:
    timestamp = int(time.time())
    message = f"{event_id}:{reg_id}:{timestamp}".encode('utf-8')
    sig = hmac.new(secret_key.encode('utf-8'), message, hashlib.sha256).hexdigest()[:16]
    return f"{reg_id}.{timestamp}.{sig}"

def verify_ticket_token(token: str, event_id: str, secret_key: str, max_age_seconds: int = 86400) -> tuple[bool, str]:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return False, "Malformed ticket token"
        reg_id, ts_str, sig = parts
        ts = int(ts_str)
        
        # Verify HMAC signature
        expected_msg = f"{event_id}:{reg_id}:{ts}".encode('utf-8')
        expected_sig = hmac.new(secret_key.encode('utf-8'), expected_msg, hashlib.sha256).hexdigest()[:16]
        
        if not hmac.compare_digest(sig, expected_sig):
            return False, "Invalid cryptographic ticket signature"
            
        return True, reg_id
    except Exception as exc:
        return False, str(exc)
```

### 2.4 File Upload Hardening
- **Path Traversal Defense:** Sanitize filenames with `secure_filename()` and append unique UUID prefix.
- **Content Inspection:** Validate file headers (magic bytes) to reject disguised executable files (`.exe`, `.sh`, `.php`, `.js`, `.py`).
- **Storage Location:** Save to isolated private directory `/uploads` or Google Cloud Storage / S3 bucket with authenticated signed URLs.

### 2.5 Security Headers & Cookie Policies
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = 'Lax'`
- `SESSION_COOKIE_SECURE = True` in production.
- Strict Content Security Policy (`CSP`) via Flask-Talisman disabling `unsafe-eval`.
- Rate limiting on authentication and checkout endpoints (`5 per minute` for login, `10 per minute` for registration submissions).
