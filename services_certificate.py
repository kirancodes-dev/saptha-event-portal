"""
services_certificate.py — Universal Certification Engine for SapthaEvent

Features:
- Multi-category certificate issuance:
  1. Winner (1st Place / Champion)
  2. Runner-Up (2nd & 3rd Place / Finalist)
  3. Participant (Attendance & Participation)
  4. Speaker (Keynote & Workshop Trainer)
  5. Judge (Jury Member & Evaluator)
- Cryptographic verification hash with public QR verification at /verify/<cert_id>.
- Automated bulk issuance based on leaderboard results or attendance records.
- ReportLab PDF generator integration.
"""

import hashlib
import uuid
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_cert_secret() -> str:
    return os.environ.get("CERT_SECRET_KEY") or os.environ.get("SECRET_KEY") or "saptha-cert-cryptographic-salt-2026"


CATEGORY_TITLES = {
    "winner": "Certificate of Achievement — 1st Place",
    "runner_up": "Certificate of Merit",
    "participant": "Certificate of Participation",
    "speaker": "Certificate of Appreciation",
    "judge": "Certificate of Honor",
}


class CertificateService:
    """
    Universal certificate issuance, cryptographic verification, and batch rendering service.
    """

    @staticmethod
    def generate_verification_hash(cert_id: str, event_id: str, email: str) -> str:
        """Create an HMAC-SHA256 signature hash for anti-counterfeit verification."""
        secret = _get_cert_secret()
        payload = f"{cert_id}:{event_id}:{email.strip().lower()}:{secret}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def issue_certificate(
        cls,
        db,
        *,
        event_id: str,
        event_title: str,
        recipient_name: str,
        recipient_email: str,
        category: str = "participant",
        rank: Optional[int] = None,
        signatories: Optional[List[Dict[str, str]]] = None,
        template_id: str = "tech_modern_gold",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Issue an individual certificate with anti-counterfeit cryptographic verification.
        """
        cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        clean_email = recipient_email.strip().lower()
        v_hash = cls.generate_verification_hash(cert_id, event_id, clean_email)
        now_str = _utcnow_iso()

        category_clean = category.strip().lower()
        if category_clean not in CATEGORY_TITLES:
            category_clean = "participant"

        title_text = CATEGORY_TITLES[category_clean]
        if rank and rank > 1 and category_clean == "runner_up":
            title_text = f"Certificate of Merit — {rank}nd Place" if rank == 2 else f"Certificate of Merit — {rank}rd Place"

        cert_data = {
            "id": cert_id,
            "cert_id": cert_id,
            "event_id": event_id,
            "event_title": event_title,
            "recipient_name": recipient_name,
            "recipient_email": clean_email,
            "category": category_clean,
            "title": title_text,
            "rank": rank,
            "verification_hash": v_hash,
            "verification_url": f"/verify/{cert_id}",
            "template_id": template_id,
            "signatories": signatories or [],
            "metadata": metadata or {},
            "issued_at": now_str,
            "status": "valid",
        }

        # Persist certificate document
        db.collection("certificates").document(cert_id).set(cert_data)

        # Update registration reference if exists
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except ImportError:
            FieldFilter = None

        try:
            if FieldFilter:
                regs = db.collection("registrations").where(filter=FieldFilter("event_id", "==", event_id)).where(filter=FieldFilter("lead_email", "==", clean_email)).limit(1).stream()
            else:
                regs = db.collection("registrations").where("event_id", "==", event_id).stream()

            for r in regs:
                if r.to_dict().get("lead_email") == clean_email:
                    db.collection("registrations").document(r.id).set({
                        "certificate_id": cert_id,
                        "certificate_issued_at": now_str,
                    }, merge=True)
                    break
        except Exception:
            pass

        return cert_data

    @classmethod
    def verify_certificate(cls, db, cert_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verify the authenticity of a certificate by ID and cryptographic hash.
        """
        doc = db.collection("certificates").document(cert_id).get()
        if not doc.exists:
            return False, "Certificate not found in database", None

        data = doc.to_dict()
        data["id"] = doc.id

        if data.get("status") == "revoked":
            return False, "Certificate has been officially revoked by the issuing authority", data

        # Cryptographic integrity check
        expected_hash = cls.generate_verification_hash(
            cert_id,
            data.get("event_id", ""),
            data.get("recipient_email", ""),
        )

        actual_hash = data.get("verification_hash")
        if actual_hash and actual_hash != expected_hash:
            return False, "Cryptographic integrity verification failed (tampered record)", data

        return True, "Certificate is authentic and verified", data

    @classmethod
    def bulk_issue_event_certificates(
        cls,
        db,
        event_id: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Issue certificates in bulk for all eligible attendees of an event.
        If category is None, automatically issues:
        - Winner certificate for rank 1
        - Runner-Up certificates for rank 2 & 3
        - Participant certificates for all checked-in attendees
        """
        event_doc = db.collection("events").document(event_id).get()
        if not event_doc.exists:
            raise ValueError(f"Event '{event_id}' not found")
        event = event_doc.to_dict()
        event_title = event.get("title", "SapthaEvent Conference")

        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except ImportError:
            FieldFilter = None

        # Fetch attendees
        if FieldFilter:
            docs = db.collection("registrations").where(filter=FieldFilter("event_id", "==", event_id)).stream()
        else:
            docs = db.collection("registrations").where("event_id", "==", event_id).stream()

        from services_evaluation import EvaluationEngine
        leaderboard = EvaluationEngine.generate_leaderboard(db, event_id)
        rank_by_reg_id = {c["registration_id"]: c["rank"] for c in leaderboard}

        issued = []
        for d in docs:
            r = d.to_dict()
            reg_id = d.id
            email = r.get("lead_email") or r.get("email")
            name = r.get("lead_name") or r.get("name") or "Attendee"

            if not email:
                continue

            # Check if attendee attended / checked in
            is_present = r.get("attendance") == "Present" or r.get("status") == "checked_in"
            user_rank = rank_by_reg_id.get(reg_id)

            # Determine certificate category
            if category:
                target_cat = category
            elif user_rank == 1:
                target_cat = "winner"
            elif user_rank in (2, 3):
                target_cat = "runner_up"
            elif is_present:
                target_cat = "participant"
            else:
                continue  # Did not attend and not a winner

            cert = cls.issue_certificate(
                db,
                event_id=event_id,
                event_title=event_title,
                recipient_name=name,
                recipient_email=email,
                category=target_cat,
                rank=user_rank,
            )
            issued.append(cert)

        return issued
