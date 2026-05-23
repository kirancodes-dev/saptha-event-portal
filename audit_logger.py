"""
audit_logger.py — Enhanced Audit Logging for SapthaEvent

Enterprise-grade audit trail with severity levels, automatic context capture,
sensitive data masking, and query capabilities.

Usage:
    from audit_logger import AuditLogger, audit_trail
    audit = AuditLogger(db)
    audit.log("EVENT_CREATED", target_type="event", target_id="abc123",
              details="Created hackathon event", severity="INFO")

    # Or as a decorator:
    @audit_trail("SCORE_SUBMITTED")
    def submit_score():
        ...
"""
import re
import logging
import datetime
import uuid
from functools import wraps

from flask import session, request, g

logger = logging.getLogger(__name__)

# Severity levels
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

# Patterns for masking sensitive data
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\b\d{10,12}\b")


def _mask_email(email: str) -> str:
    """Mask email: john.doe@gmail.com → j*****e@g***l.com"""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _mask_phone(phone: str) -> str:
    """Mask phone: 9876543210 → 98*****210"""
    if len(phone) < 6:
        return phone
    return phone[:2] + "*" * (len(phone) - 5) + phone[-3:]


def mask_sensitive(text: str) -> str:
    """Mask emails and phone numbers in text."""
    result = _EMAIL_RE.sub(lambda m: _mask_email(m.group()), text)
    result = _PHONE_RE.sub(lambda m: _mask_phone(m.group()), result)
    return result


class AuditLogger:
    """Enhanced audit logger with automatic context capture."""

    def __init__(self, db):
        self.db = db
        self.collection = "audit_log_v2"

    def log(
        self,
        action: str,
        *,
        target_type: str = "",
        target_id: str = "",
        details: str = "",
        severity: str = SEVERITY_INFO,
        metadata: dict = None,
        mask_details: bool = True,
    ) -> str:
        """Write an immutable audit entry.

        Args:
            action: Action identifier (e.g., EVENT_CREATED, LOGIN_SUCCESS)
            target_type: Type of entity affected (event, user, registration)
            target_id: ID of the affected entity
            details: Human-readable description
            severity: INFO, WARNING, or CRITICAL
            metadata: Additional structured data
            mask_details: Whether to mask PII in details

        Returns:
            The audit log entry ID
        """
        log_id = str(uuid.uuid4())

        if mask_details and details:
            details = mask_sensitive(details)

        entry = {
            "id": log_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "severity": severity,
            # Actor context (automatic)
            "actor_email": session.get("user_id", "system"),
            "actor_role": session.get("role", "system"),
            "actor_ip": request.remote_addr if request else "0.0.0.0",
            "actor_user_agent": (request.headers.get("User-Agent", "")[:200]
                                 if request else ""),
            # Organization context
            "org_id": (getattr(g, "org", {}) or {}).get("id", "")
                      if hasattr(g, "org") else "",
            # Metadata
            "metadata": metadata or {},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        try:
            self.db.collection(self.collection).document(log_id).set(entry)
        except Exception as exc:
            # Never let audit logging crash the application
            logger.error("Audit log write failed: %s", exc)

        # Also log to application logger for observability
        log_msg = f"[AUDIT] {severity} | {action} | {target_type}:{target_id} | {details}"
        if severity == SEVERITY_CRITICAL:
            logger.critical(log_msg)
        elif severity == SEVERITY_WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return log_id

    def log_batch(self, entries: list) -> int:
        """Write multiple audit entries in a batch.

        Each entry should be a dict with at least 'action' key.
        """
        if not entries:
            return 0

        batch = self.db.batch()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        count = 0

        for entry_data in entries:
            log_id = str(uuid.uuid4())
            entry = {
                "id": log_id,
                "action": entry_data.get("action", "UNKNOWN"),
                "target_type": entry_data.get("target_type", ""),
                "target_id": entry_data.get("target_id", ""),
                "details": mask_sensitive(entry_data.get("details", "")),
                "severity": entry_data.get("severity", SEVERITY_INFO),
                "actor_email": session.get("user_id", "system"),
                "actor_role": session.get("role", "system"),
                "actor_ip": request.remote_addr if request else "0.0.0.0",
                "org_id": "",
                "metadata": entry_data.get("metadata", {}),
                "timestamp": now,
            }
            ref = self.db.collection(self.collection).document(log_id)
            batch.set(ref, entry)
            count += 1

        try:
            batch.commit()
        except Exception as exc:
            logger.error("Audit batch write failed: %s", exc)
            count = 0

        return count

    def query(
        self,
        *,
        action: str = "",
        actor_email: str = "",
        target_type: str = "",
        severity: str = "",
        since: str = "",
        limit: int = 100,
    ) -> list:
        """Query audit logs with filters."""
        query = self.db.collection(self.collection)

        if action:
            query = query.where("action", "==", action)
        if actor_email:
            query = query.where("actor_email", "==", actor_email)
        if target_type:
            query = query.where("target_type", "==", target_type)
        if severity:
            query = query.where("severity", "==", severity)
        if since:
            query = query.where("timestamp", ">=", since)

        query = query.order_by("timestamp", direction="DESCENDING").limit(limit)

        results = []
        for doc in query.stream():
            entry = doc.to_dict()
            entry["id"] = doc.id
            results.append(entry)

        return results


def audit_trail(action: str, severity: str = SEVERITY_INFO, target_type: str = ""):
    """Decorator that automatically logs a route to the audit trail.

    Usage::

        @app.route('/admin/delete-user/<uid>')
        @audit_trail('USER_DELETED', severity='CRITICAL', target_type='user')
        def delete_user(uid):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = f(*args, **kwargs)

            try:
                from app import db
                if db:
                    auditor = AuditLogger(db)
                    target_id = kwargs.get("event_id") or kwargs.get("user_id") or kwargs.get("id", "")
                    auditor.log(
                        action,
                        target_type=target_type,
                        target_id=str(target_id),
                        details=f"{request.method} {request.path}",
                        severity=severity,
                    )
            except Exception as exc:
                logger.error("Audit trail decorator error: %s", exc)

            return result
        return decorated
    return decorator
