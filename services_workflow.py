"""
services_workflow.py — Configurable Workflow State Machine & Audit Engine for SapthaEvent

Features:
- Event Lifecycle DAG state machine with guarded transitions.
- Participant / Registration workflow state machine with guarded prerequisites.
- Immutable audit log tracking for all state mutations.
- Custom validation guards (e.g. payment confirmation, capacity, check-in validation).
- Queryable history for compliance, disputes, and analytics.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# 1. State Definitions & Permitted Transitions
# ----------------------------------------------------------------------

EVENT_STATE_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["published", "cancelled"],
    "published": ["registration_open", "draft", "cancelled"],
    "registration_open": ["registration_closed", "in_progress", "cancelled"],
    "registration_closed": ["registration_open", "in_progress", "cancelled"],
    "in_progress": ["evaluation", "completed", "cancelled"],
    "evaluation": ["completed", "in_progress", "cancelled"],
    "completed": ["archived"],
    "archived": ["published"],
    "cancelled": ["draft"],
}

PARTICIPANT_STATE_TRANSITIONS: Dict[str, List[str]] = {
    "applied": ["pending_payment", "confirmed", "waitlisted", "cancelled"],
    "pending_payment": ["confirmed", "waitlisted", "cancelled"],
    "waitlisted": ["confirmed", "cancelled"],
    "confirmed": ["checked_in", "cancelled"],
    "checked_in": ["round_1", "shortlisted", "completed", "cancelled"],
    "round_1": ["shortlisted", "eliminated", "completed"],
    "shortlisted": ["finalist", "winner", "runner_up", "eliminated", "completed"],
    "finalist": ["winner", "runner_up", "completed"],
    "winner": ["certified", "completed"],
    "runner_up": ["certified", "completed"],
    "completed": ["certified"],
    "eliminated": ["completed"],
    "certified": [],
    "cancelled": ["applied", "confirmed"],  # Admin restore
}


class WorkflowError(Exception):
    """Raised when an illegal or guarded workflow transition is attempted."""
    pass


class WorkflowEngine:
    """
    Guarded workflow execution engine with transition validation and audit logging.
    """

    # ------------------------------------------------------------------
    # Event Lifecycle Methods
    # ------------------------------------------------------------------

    @staticmethod
    def can_transition_event(current_state: str, target_state: str) -> Tuple[bool, str]:
        """
        Check whether an event transition is permitted by the state machine.
        """
        c_state = (current_state or "draft").strip().lower()
        t_state = target_state.strip().lower()

        if c_state == t_state:
            return True, f"Event is already in '{c_state}' state."

        allowed = EVENT_STATE_TRANSITIONS.get(c_state, [])
        if t_state in allowed:
            return True, "Transition allowed."

        return False, (
            f"Invalid event transition: cannot move from '{c_state}' to '{t_state}'. "
            f"Allowed target states: {allowed}"
        )

    @classmethod
    def transition_event(
        cls,
        db,
        *,
        event_id: str,
        target_state: str,
        actor_id: str = "system",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute an event lifecycle transition, write audit log, and return updated event.
        """
        doc_ref = db.collection("events").document(event_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise WorkflowError(f"Event '{event_id}' not found.")

        event_data = doc.to_dict()
        event_data["id"] = doc.id
        current_state = event_data.get("status", "draft")

        t_state = target_state.strip().lower()

        if not force:
            allowed, msg = cls.can_transition_event(current_state, t_state)
            if not allowed:
                raise WorkflowError(msg)

        # Update event status
        now_str = _utcnow_iso()
        updates = {
            "status": t_state,
            "updated_at": now_str,
        }

        # Track stage timestamps
        stage_timestamps = event_data.get("stage_timestamps", {})
        stage_timestamps[t_state] = now_str
        updates["stage_timestamps"] = stage_timestamps

        doc_ref.set(updates, merge=True)
        event_data.update(updates)

        # Record immutable audit log
        cls._record_audit_entry(
            db,
            entity_type="event",
            entity_id=event_id,
            from_state=current_state,
            to_state=t_state,
            actor_id=actor_id,
            reason=reason or f"Event lifecycle transition to '{t_state}'",
            metadata=metadata or {},
        )

        return event_data

    # ------------------------------------------------------------------
    # Participant / Registration Lifecycle Methods
    # ------------------------------------------------------------------

    @staticmethod
    def can_transition_participant(
        current_state: str,
        target_state: str,
        reg_data: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Check whether a participant transition is valid and satisfies domain guards.
        """
        if force:
            return True, "Forced transition permitted by administrator."

        c_state = (current_state or "applied").strip().lower()
        t_state = target_state.strip().lower()

        if c_state == t_state:
            return True, f"Participant is already in '{c_state}' state."

        # Guard: Cannot move to checked_in unless currently confirmed
        if t_state == "checked_in" and c_state != "confirmed":
            return False, f"Cannot check in participant from '{c_state}' state. Must be 'confirmed'."

        allowed = PARTICIPANT_STATE_TRANSITIONS.get(c_state, [])
        if t_state not in allowed:
            return False, (
                f"Invalid participant transition: cannot move from '{c_state}' to '{t_state}'. "
                f"Allowed states: {allowed}"
            )

        # Guard: Paid events require payment confirmation
        if reg_data and t_state == "confirmed":
            fee = float(reg_data.get("fee", 0.0) or 0.0)
            payment_status = reg_data.get("payment_status", "unpaid")
            if fee > 0 and payment_status not in ("paid", "completed", "exempt"):
                return False, f"Cannot confirm participant with outstanding payment (fee: {fee}, status: {payment_status})."

        return True, "Transition allowed."

    @classmethod
    def transition_participant(
        cls,
        db,
        *,
        registration_id: str,
        target_state: str,
        actor_id: str = "system",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute participant workflow transition with audit logging.
        """
        doc_ref = db.collection("registrations").document(registration_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise WorkflowError(f"Registration '{registration_id}' not found.")

        reg_data = doc.to_dict()
        reg_data["id"] = doc.id
        current_state = reg_data.get("status", "applied")

        t_state = target_state.strip().lower()

        allowed, msg = cls.can_transition_participant(
            current_state, t_state, reg_data=reg_data, force=force
        )
        if not allowed:
            raise WorkflowError(msg)

        now_str = _utcnow_iso()
        updates = {
            "status": t_state,
            "updated_at": now_str,
        }

        # If transitioning to checked_in, record checkin metadata
        if t_state == "checked_in":
            updates["checked_in"] = True
            updates["checked_in_at"] = now_str
            updates["checked_in_by"] = actor_id

        doc_ref.set(updates, merge=True)
        reg_data.update(updates)

        # Record immutable audit log
        cls._record_audit_entry(
            db,
            entity_type="registration",
            entity_id=registration_id,
            from_state=current_state,
            to_state=t_state,
            actor_id=actor_id,
            reason=reason or f"Participant workflow transition to '{t_state}'",
            metadata=metadata or {},
        )

        return reg_data

    # ------------------------------------------------------------------
    # Audit Logging & History
    # ------------------------------------------------------------------

    @staticmethod
    def _record_audit_entry(
        db,
        *,
        entity_type: str,
        entity_id: str,
        from_state: str,
        to_state: str,
        actor_id: str,
        reason: str,
        metadata: Dict[str, Any],
    ) -> str:
        """Persist an immutable audit log entry."""
        audit_id = f"wf_{uuid.uuid4().hex[:16]}"
        entry = {
            "id": audit_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor_id": actor_id,
            "reason": reason,
            "metadata": metadata,
            "timestamp": _utcnow_iso(),
        }
        try:
            db.collection("workflow_audit_logs").document(audit_id).set(entry)
        except Exception:
            # Fallback to general audit_logs if needed
            try:
                db.collection("audit_logs").document(audit_id).set(entry)
            except Exception:
                pass
        return audit_id

    @staticmethod
    def get_workflow_history(db, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve chronological workflow transition history for an entity.
        """
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except ImportError:
            FieldFilter = None

        query = db.collection("workflow_audit_logs")
        if FieldFilter:
            query = query.where(filter=FieldFilter("entity_id", "==", entity_id))
        else:
            query = query.where("entity_id", "==", entity_id)

        entries = []
        for doc in query.stream():
            d = doc.to_dict()
            d["id"] = doc.id
            if d.get("entity_type") == entity_type:
                entries.append(d)

        # Sort chronologically
        entries.sort(key=lambda x: x.get("timestamp", ""))
        return entries
