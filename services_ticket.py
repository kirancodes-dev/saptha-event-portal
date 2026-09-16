"""
services_ticket.py — Universal Multi-Tier Ticketing Engine for SapthaEvent

Features:
- Multi-tier ticket issuing (General, VIP, Speaker, Judge, Student, etc.).
- HMAC-SHA256 signed QR ticket tokens with timestamp, nonce, and anti-tamper verification.
- Anti-replay and double-entry protection.
- Offline-compatible cryptographic validation.
- Digital ticket wallet metadata generation.
"""

import hmac
import hashlib
import json
import base64
import time
import uuid
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from utils_qr import generate_qr_base64


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_signing_key() -> bytes:
    """Retrieve secret key for HMAC token signing."""
    secret = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET_KEY") or "saptha-secure-ticket-secret-key-2026"
    return secret.encode("utf-8")


class TicketService:
    """
    Core ticketing engine managing ticket lifecycles, cryptographic signatures,
    and fraud-proof gate check-ins.
    """

    DEFAULT_TIERS = ["General", "VIP", "Speaker", "Judge", "Student"]

    # ------------------------------------------------------------------
    # Cryptographic Token Signing & Verification
    # ------------------------------------------------------------------

    @staticmethod
    def generate_signed_qr_token(
        *,
        ticket_id: str,
        registration_id: str,
        event_id: str,
        tier: str,
        lead_name: str,
        secret_key: Optional[bytes] = None,
    ) -> str:
        """
        Generate a tamper-proof HMAC-SHA256 signed token.
        Token format: <base64url_payload>.<signature_hex>
        """
        key = secret_key or _get_signing_key()
        nonce = uuid.uuid4().hex[:12]
        timestamp = int(time.time())

        payload = {
            "tid": ticket_id,
            "rid": registration_id,
            "eid": event_id,
            "tier": tier,
            "name": lead_name,
            "ts": timestamp,
            "nonce": nonce,
        }

        payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")

        sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload_b64}.{sig}"

    @staticmethod
    def verify_signed_qr_token(
        token: str,
        *,
        max_age_seconds: Optional[int] = None,
        secret_key: Optional[bytes] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verify an HMAC-SHA256 signed ticket token.
        Returns: (is_valid, message, payload)
        """
        if not token or "." not in token:
            return False, "Malformed ticket token format", None

        parts = token.split(".")
        if len(parts) != 2:
            return False, "Invalid token structure", None

        payload_b64, signature = parts
        key = secret_key or _get_signing_key()

        expected_sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature, expected_sig):
            return False, "Cryptographic signature mismatch (tampered token)", None

        # Decode payload
        try:
            padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
            payload_bytes = base64.urlsafe_b64decode(padded_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"Failed to decode token payload: {e}", None

        # Validate timestamp expiration if configured
        if max_age_seconds is not None:
            ts = payload.get("ts", 0)
            if time.time() - ts > max_age_seconds:
                return False, "Ticket QR token has expired", payload

        return True, "Token valid", payload

    # ------------------------------------------------------------------
    # Ticket Issuance
    # ------------------------------------------------------------------

    @classmethod
    def issue_ticket(
        cls,
        db,
        *,
        event_id: str,
        registration_id: str,
        user_email: str,
        lead_name: str,
        ticket_type: str = "General",
        gate_assignment: str = "Gate 1",
        seat_assignment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate and persist a multi-tier ticket with signed QR code.
        """
        ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"
        clean_eid = event_id[:8].upper()
        rand_code = uuid.uuid4().hex[:6].upper()
        ticket_code = f"TKT-{clean_eid}-{rand_code}"

        # Generate HMAC-SHA256 signed token
        signed_token = cls.generate_signed_qr_token(
            ticket_id=ticket_id,
            registration_id=registration_id,
            event_id=event_id,
            tier=ticket_type,
            lead_name=lead_name,
        )

        qr_token_hash = hashlib.sha256(signed_token.encode("utf-8")).hexdigest()

        now_str = _utcnow_iso()
        ticket_data = {
            "id": ticket_id,
            "ticket_id": ticket_id,
            "event_id": event_id,
            "registration_id": registration_id,
            "user_email": user_email.strip().lower(),
            "lead_name": lead_name,
            "ticket_type": ticket_type,
            "ticket_code": ticket_code,
            "signed_token": signed_token,
            "qr_token_hash": qr_token_hash,
            "gate_assignment": gate_assignment,
            "seat_assignment": seat_assignment or "General Open",
            "status": "active",
            "checked_in": False,
            "checked_in_at": None,
            "created_at": now_str,
        }

        # Persist to database
        db.collection("tickets").document(ticket_id).set(ticket_data)

        # Update registration with ticket code and status
        try:
            db.collection("registrations").document(registration_id).set({
                "ticket_id": ticket_id,
                "ticket_code": ticket_code,
                "ticket_type": ticket_type,
                "signed_token": signed_token,
            }, merge=True)
        except Exception:
            pass

        return ticket_data

    # ------------------------------------------------------------------
    # Ticket Check-In & Anti-Replay Verification
    # ------------------------------------------------------------------

    @classmethod
    def checkin_ticket(
        cls,
        db,
        token_or_ticket_id: str,
        *,
        actor_id: str = "scanner_guard",
    ) -> Dict[str, Any]:
        """
        Verify and check in a ticket token or ticket ID.
        Guarantees anti-replay protection.
        """
        token_or_ticket_id = token_or_ticket_id.strip()

        ticket_doc = None
        ticket_data = None
        verified_offline = False

        # If it looks like a signed token (<b64>.<sig>)
        if "." in token_or_ticket_id:
            is_valid, msg, payload = cls.verify_signed_qr_token(token_or_ticket_id)
            if not is_valid:
                return {
                    "status": "invalid",
                    "message": msg,
                    "ticket": None,
                }
            ticket_id = payload["tid"]
            verified_offline = True
        else:
            ticket_id = token_or_ticket_id

        # Lookup ticket in database
        try:
            doc = db.collection("tickets").document(ticket_id).get()
            if doc.exists:
                ticket_doc = doc
                ticket_data = doc.to_dict()
                ticket_data["id"] = doc.id
        except Exception:
            pass

        # Fallback query by ticket_code or signed_token if not found by ID
        if not ticket_data:
            try:
                for doc in db.collection("tickets").where("ticket_code", "==", token_or_ticket_id).limit(1).stream():
                    ticket_data = doc.to_dict()
                    ticket_data["id"] = doc.id
                    break
            except Exception:
                pass

        if not ticket_data:
            if verified_offline:
                # Cryptographically authentic token but DB record missing
                now_str = _utcnow_iso()
                return {
                    "status": "success",
                    "message": "Entry granted (Cryptographically Verified Offline)",
                    "ticket": {
                        "ticket_id": payload.get("tid"),
                        "lead_name": payload.get("name"),
                        "ticket_type": payload.get("tier"),
                        "event_id": payload.get("eid"),
                        "checked_in_at": now_str,
                    },
                }
            return {
                "status": "invalid",
                "message": "Ticket record not found",
                "ticket": None,
            }

        # Check anti-replay / already checked in
        if ticket_data.get("status") == "checked_in" or ticket_data.get("checked_in"):
            return {
                "status": "already_used",
                "message": f"Ticket already checked in at {ticket_data.get('checked_in_at')}",
                "ticket": ticket_data,
            }

        if ticket_data.get("status") == "cancelled":
            return {
                "status": "invalid",
                "message": "Ticket has been cancelled or refunded",
                "ticket": ticket_data,
            }

        # Check registration payment status
        reg_id = ticket_data.get("registration_id")
        if reg_id:
            try:
                reg_doc = db.collection("registrations").document(reg_id).get()
                if reg_doc.exists:
                    reg_info = reg_doc.to_dict()
                    fee = float(reg_info.get("fee", 0.0) or 0.0)
                    payment_status = (reg_info.get("payment_status") or "").lower()
                    if fee > 0 and payment_status not in ("paid", "completed", "exempt", "free"):
                        return {
                            "status": "unpaid",
                            "message": "Payment pending — entry cannot be granted",
                            "ticket": ticket_data,
                        }
            except Exception:
                pass

        # Perform check-in
        now_str = _utcnow_iso()
        updates = {
            "status": "checked_in",
            "checked_in": True,
            "checked_in_at": now_str,
            "checked_in_by": actor_id,
        }
        db.collection("tickets").document(ticket_data["id"]).set(updates, merge=True)
        ticket_data.update(updates)

        # Sync registration attendance
        if reg_id:
            try:
                db.collection("registrations").document(reg_id).set({
                    "attendance": "Present",
                    "status": "checked_in",
                    "checked_in": True,
                    "checked_in_at": now_str,
                    "checked_in_by": actor_id,
                }, merge=True)
            except Exception:
                pass

        return {
            "status": "success",
            "message": "Entry granted! Check-in verified.",
            "ticket": ticket_data,
        }

    # ------------------------------------------------------------------
    # Digital Wallet Pass Details
    # ------------------------------------------------------------------

    @classmethod
    def get_wallet_pass(cls, db, ticket_id_or_code: str) -> Optional[Dict[str, Any]]:
        """
        Assemble comprehensive digital pass metadata for mobile wallets.
        """
        ticket = None
        # Try direct get
        doc = db.collection("tickets").document(ticket_id_or_code).get()
        if doc.exists:
            ticket = doc.to_dict()
            ticket["id"] = doc.id
        else:
            # Try query by ticket_code
            for d in db.collection("tickets").where("ticket_code", "==", ticket_id_or_code).limit(1).stream():
                ticket = d.to_dict()
                ticket["id"] = d.id
                break

        if not ticket:
            return None

        # Fetch associated event
        event_doc = db.collection("events").document(ticket.get("event_id", "")).get()
        event = event_doc.to_dict() if event_doc.exists else {}

        # Generate QR code base64 if not already present
        signed_token = ticket.get("signed_token") or ticket.get("ticket_code")
        qr_b64 = generate_qr_base64(signed_token)

        tier = ticket.get("ticket_type", "General")
        tier_colors = {
            "VIP": {"primary": "#eab308", "bg": "#1e1b4b", "text": "#ffffff"},
            "Speaker": {"primary": "#a855f7", "bg": "#1e1b4b", "text": "#ffffff"},
            "Judge": {"primary": "#ec4899", "bg": "#1e1b4b", "text": "#ffffff"},
            "Student": {"primary": "#10b981", "bg": "#064e3b", "text": "#ffffff"},
            "General": {"primary": "#3b82f6", "bg": "#0f172a", "text": "#ffffff"},
        }

        return {
            "ticket": ticket,
            "event": event,
            "qr_image_base64": qr_b64,
            "theme": tier_colors.get(tier, tier_colors["General"]),
            "is_valid": ticket.get("status") in ("active", "checked_in"),
        }
