"""
security_guard.py — Zero-Trust Security Guard & Object-Level Access Control (Phase 10)

Provides:
1. Object-Level Access Control (OLAC / IDOR Defense):
   - verify_registration_access: restricts ticket and form access to attendee, team members, or authorized organizers.
2. File Upload Hardening:
   - Path traversal prevention, extension whitelist, MIME magic check, and file size guard.
3. Cryptographic Time-Bound Nonce & Anti-Replay:
   - generate_time_bound_nonce and verify_time_bound_nonce.
4. Security Audit & Incident Logging:
   - log_security_incident for tamper attempts, permission denials, and rate violations.
"""

import os
import re
import time
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "zip", "txt", "csv"
}

DANGEROUS_EXTENSIONS = {
    "exe", "sh", "bat", "cmd", "php", "phtml", "py", "pl", "rb", "js", "html", "htm", "svg"
}

MAGIC_HEADER_SIGNATURES = {
    "pdf": b"%PDF-",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "zip": b"PK\x03\x04",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SecurityGuard:
    """
    Zero-Trust Security utilities for SapthaEvent.
    """

    @staticmethod
    def verify_registration_access(
        registration_dict: Dict[str, Any],
        user_email: str,
        user_role: str,
    ) -> bool:
        """
        Verify whether the requesting user has legitimate access to this registration record.
        Prevents Insecure Direct Object Reference (IDOR).
        """
        if not user_email:
            return False

        clean_user = user_email.strip().lower()
        role_clean = (user_role or "").strip().lower()

        # Administrative and organizing staff have global access
        if role_clean in ("superadmin", "admin", "spoc", "eventcoordinator", "coordinator", "organizer"):
            return True

        # Lead attendee has access
        lead = (registration_dict.get("lead_email") or registration_dict.get("email") or "").strip().lower()
        if lead and lead == clean_user:
            return True

        # Team members have access
        members = registration_dict.get("members") or []
        for m in members:
            if isinstance(m, dict):
                m_email = (m.get("email") or "").strip().lower()
                if m_email and m_email == clean_user:
                    return True
            elif isinstance(m, str) and m.strip().lower() == clean_user:
                return True

        return False

    @staticmethod
    def validate_file_upload(
        filename: str,
        content_bytes: Optional[bytes] = None,
        max_size_mb: int = 10,
    ) -> Tuple[bool, str]:
        """
        Comprehensive upload defense: path traversal, dangerous extensions, and magic byte validation.
        """
        if not filename or not filename.strip():
            return False, "Filename cannot be empty"

        # Check for path traversal attempts
        if ".." in filename or "/" in filename or "\\" in filename:
            return False, "Path traversal sequence detected in filename"

        # Extract extension
        parts = filename.rsplit(".", 1)
        if len(parts) < 2:
            return False, "File must have an explicit extension"

        ext = parts[1].lower().strip()
        if ext in DANGEROUS_EXTENSIONS:
            return False, f"Executable or script extension '.{ext}' is strictly prohibited"

        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Extension '.{ext}' is not in the permitted whitelist"

        # Check content size if provided
        if content_bytes is not None:
            size_mb = len(content_bytes) / (1024 * 1024)
            if size_mb > max_size_mb:
                return False, f"File size ({size_mb:.1f} MB) exceeds maximum permitted limit ({max_size_mb} MB)"

            # Magic header verification for common binary formats
            if ext in MAGIC_HEADER_SIGNATURES:
                expected_magic = MAGIC_HEADER_SIGNATURES[ext]
                if not content_bytes.startswith(expected_magic):
                    return False, f"File content does not match reported extension '.{ext}' (spoofed MIME magic)"

        return True, "File is valid and secure"

    @staticmethod
    def generate_time_bound_nonce(
        subject: str,
        secret_key: str,
        ttl_seconds: int = 300,
    ) -> str:
        """
        Generate a cryptographic anti-replay nonce valid for a limited time window (e.g. 5 minutes).
        Format: <timestamp>.<hex_hash>
        """
        ts = int(time.time())
        msg = f"{subject}:{ts}:{ttl_seconds}".encode("utf-8")
        sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]
        return f"{ts}.{ttl_seconds}.{sig}"

    @staticmethod
    def verify_time_bound_nonce(
        nonce: str,
        subject: str,
        secret_key: str,
    ) -> Tuple[bool, str]:
        """
        Verify anti-replay nonce validity and expiration.
        """
        try:
            parts = nonce.split(".")
            if len(parts) != 3:
                return False, "Malformed nonce structure"

            ts_str, ttl_str, sig = parts
            ts = int(ts_str)
            ttl = int(ttl_str)

            now = int(time.time())
            if now - ts > ttl:
                return False, "Nonce has expired (time window elapsed)"
            if ts > now + 30:  # Allow 30s clock drift
                return False, "Nonce timestamp is in the future"

            expected_msg = f"{subject}:{ts}:{ttl}".encode("utf-8")
            expected_sig = hmac.new(secret_key.encode("utf-8"), expected_msg, hashlib.sha256).hexdigest()[:16]

            if not hmac.compare_digest(sig, expected_sig):
                return False, "Cryptographic signature verification failed"

            return True, "Nonce valid"
        except Exception as e:
            return False, f"Nonce verification error: {e}"

    @staticmethod
    def log_security_incident(
        db,
        *,
        incident_type: str,
        actor_email: str,
        ip_address: str = "127.0.0.1",
        severity: str = "HIGH",
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record security incidents to the security audit trail.
        """
        incident_id = f"sec_{uuid.uuid4().hex[:12]}"
        now_str = _utcnow_iso()

        record = {
            "id": incident_id,
            "incident_type": incident_type,
            "actor_email": actor_email.strip().lower() if actor_email else "anonymous",
            "ip_address": ip_address,
            "severity": severity.upper(),
            "details": details or {},
            "timestamp": now_str,
        }
        db.collection("security_incidents").document(incident_id).set(record)
        return incident_id
