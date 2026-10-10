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
    "draft": ["pending_approval", "published", "cancelled"],
    "pending_approval": ["published", "draft", "cancelled"],
    "published": ["registration_open", "draft", "cancelled"],
    "registration_open": ["registration_closed", "in_progress", "cancelled"],
    "registration_closed": ["registration_open", "in_progress", "cancelled"],
    "in_progress": ["evaluation", "completed", "cancelled"],
    "evaluation": ["completed", "in_progress", "cancelled"],
    "completed": ["certified", "archived"],
    "certified": ["archived"],
    "archived": ["published"],
    "cancelled": ["draft"],
    # For legacy events
    "active": ["completed", "cancelled"],
    "inactive": ["active", "draft"],
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


# Statuses in which an event can run on its day (scanners, walk-ins, self
# check-in, reminders): every published state up to `in_progress`, plus the old
# single `active` status. Not draft, pending approval, cancelled or completed.
EVENT_DAY_STATUSES = ('published', 'registration_open', 'registration_closed', 'in_progress', 'active')

# Statuses in which an event is still taking registrations.
REGISTRATION_OPEN_STATUSES = ('registration_open', 'active')


def is_event_day_status(event: Optional[Dict[str, Any]]) -> bool:
    """True when the event's status lets it run on its day."""
    return str((event or {}).get('status') or '').lower() in EVENT_DAY_STATUSES


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

    @classmethod
    def get_allowed_transitions(
        cls,
        event_data: Optional[Dict[str, Any]] = None,
        current_state: Optional[str] = None
    ) -> List[str]:
        """
        Determine allowed target states for an event using its per-event workflow config,
        falling back to global EVENT_STATE_TRANSITIONS.
        """
        event_data = event_data or {}
        c_state = (current_state or event_data.get("status") or "draft").strip().lower()

        wf_cfg = event_data.get("workflow_config")
        if isinstance(wf_cfg, str):
            try:
                import json
                wf_cfg = json.loads(wf_cfg)
            except Exception:
                wf_cfg = None

        if isinstance(wf_cfg, dict):
            # Explicit transitions map in per-event workflow config
            if "transitions" in wf_cfg and isinstance(wf_cfg["transitions"], dict):
                allowed_from_cfg = wf_cfg["transitions"].get(c_state)
                if allowed_from_cfg is not None:
                    return list(allowed_from_cfg)

            # Stages list in per-event workflow config (strict sequential progression)
            stages = wf_cfg.get("stages")
            if isinstance(stages, list) and stages:
                stages_lower = [str(s).strip().lower() for s in stages]
                if c_state in stages_lower:
                    idx = stages_lower.index(c_state)
                    allowed = []
                    # Strictly allow next stage (prevents state skipping)
                    if idx + 1 < len(stages_lower):
                        allowed.append(stages_lower[idx + 1])
                    # Revert to draft from published
                    if c_state == "published" and "draft" in stages_lower and "draft" not in allowed:
                        allowed.append("draft")
                    # Re-open registration from closed
                    if c_state == "registration_closed" and "registration_open" in stages_lower and "registration_open" not in allowed:
                        allowed.append("registration_open")
                    # Cancellation from active non-terminal stages
                    if c_state not in ("completed", "certified", "archived", "cancelled"):
                        allowed.append("cancelled")
                    # Re-open from cancelled
                    if c_state == "cancelled" and "draft" in stages_lower:
                        allowed.append("draft")
                    return allowed

        # Fallback to global EVENT_STATE_TRANSITIONS
        return list(EVENT_STATE_TRANSITIONS.get(c_state, []))

    @classmethod
    def can_transition_event(
        cls,
        current_state: str,
        target_state: str,
        event_data: Optional[Dict[str, Any]] = None,
        actor: Optional[Any] = None,
        db: Optional[Any] = None,
    ) -> Tuple[bool, str]:
        """
        Check whether an event transition is permitted by the per-event or global state machine,
        including institutional approval guards for unit-created events.
        """
        c_state = (current_state or "draft").strip().lower()
        t_state = target_state.strip().lower()

        if c_state == t_state:
            return True, f"Event is already in '{c_state}' state."

        allowed = cls.get_allowed_transitions(event_data=event_data, current_state=c_state)
        if t_state not in allowed:
            return False, (
                f"Invalid event transition: cannot move from '{c_state}' to '{t_state}'. "
                f"Allowed target states: {allowed}"
            )

        # ── Approval Guard for Unit-Created Events ──
        if event_data:
            org_unit_id = event_data.get("org_unit_id") or event_data.get("orgUnitId")
            is_unit_event = bool(org_unit_id and str(org_unit_id).lower() not in ("central", "none", ""))

            if is_unit_event:
                from services_permission import can

                # 1. Draft to Published: requires approval unless actor has approve_event permission
                if c_state == "draft" and t_state == "published":
                    if actor and can(actor, "approve_event", event_data, db=db):
                        return True, "Transition allowed (approved by authorized administrator)."
                    return False, "Unit-created events require approval before publishing. Please submit for approval ('pending_approval') first."

                # 2. Pending Approval to Published: must be approved by authorized role
                if c_state == "pending_approval" and t_state == "published":
                    if actor and can(actor, "approve_event", event_data, db=db):
                        pass  # Approved, continue to room check
                    else:
                        return False, "Approval required: Actor is not authorized to approve this event for publication."

        # ── Room Conflict Guard for Publishing ──
        if t_state == "published" and db and event_data:
            from services_venue import check_room_conflict
            ev_id = event_data.get("id")
            room_id = event_data.get("room_id") or event_data.get("roomId")

            # Check if there is a booking in venue_bookings for this event
            bookings = list(db.collection("venue_bookings").where("event_id", "==", str(ev_id)).stream()) if ev_id else []
            if bookings:
                for b in bookings:
                    bd = b.to_dict()
                    b_room = bd.get("room_id") or bd.get("roomId")
                    b_start = bd.get("start_time") or bd.get("startTime")
                    b_end = bd.get("end_time") or bd.get("endTime")
                    b_status = (bd.get("status") or "confirmed").strip().lower()
                    if b_room and b_start and b_end and b_status != "cancelled":
                        has_clash, clash_info = check_room_conflict(
                            db,
                            room_id=b_room,
                            start_time=b_start,
                            end_time=b_end,
                            exclude_booking_id=b.id,
                            exclude_event_id=ev_id,
                        )
                        if has_clash and clash_info:
                            return False, clash_info.get("message", "Cannot publish event due to room booking conflict.")
            elif room_id:
                start_dt = event_data.get("start_datetime") or event_data.get("startDatetime") or event_data.get("date")
                end_dt = event_data.get("end_datetime") or event_data.get("endDatetime") or start_dt
                if start_dt and end_dt:
                    has_clash, clash_info = check_room_conflict(
                        db,
                        room_id=room_id,
                        start_time=start_dt,
                        end_time=end_dt,
                        exclude_event_id=ev_id,
                    )
                    if has_clash and clash_info:
                        return False, clash_info.get("message", "Cannot publish event due to room booking conflict.")

        return True, "Transition allowed."

    @classmethod
    def transition_event(
        cls,
        db,
        *,
        event_id: str,
        target_state: str,
        actor_id: str = "system",
        actor: Optional[Any] = None,
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
            effective_actor = actor or actor_id
            allowed, msg = cls.can_transition_event(
                current_state, t_state, event_data=event_data, actor=effective_actor, db=db
            )
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

        # Trigger change notifications when cancelled
        if t_state == "cancelled" and current_state != "cancelled":
            cls._notify_participants_of_cancellation(db, event_id=event_id, event_data=event_data)

        return event_data

    @classmethod
    def _notify_participants_of_cancellation(cls, db, *, event_id: str, event_data: Dict[str, Any]):
        """Notify registered participants when an event is cancelled, exactly once per participant."""
        try:
            from services_automation import NotificationAutomationEngine
            regs = list(db.collection("registrations").where("event_id", "==", str(event_id)).stream())
            notified_emails = set()
            event_title = event_data.get("title") or event_data.get("name") or "Event"
            date_str = event_data.get("date") or event_data.get("start_datetime") or ""

            for r in regs:
                rd = r.to_dict()
                if (rd.get("status") or "").strip().lower() == "cancelled":
                    continue
                email = (rd.get("lead_email") or rd.get("student_email") or "").strip().lower()
                if email and email not in notified_emails:
                    notified_emails.add(email)
                    recipient_name = rd.get("lead_name") or rd.get("name") or "Participant"
                    context = {
                        "recipient_email": email,
                        "recipient_name": recipient_name,
                        "event_title": event_title,
                        "date": date_str,
                    }
                    custom_rule = {
                        "title": f"Cancelled: {event_title}",
                        "message": f"Hello {recipient_name}, the event '{event_title}' scheduled for {date_str} has been cancelled.",
                        "notif_type": "system_alert",
                        "channels": ["in_app", "email"],
                    }
                    NotificationAutomationEngine.dispatch_trigger(
                        db,
                        trigger_name="on_event_cancelled",
                        context=context,
                        custom_rule=custom_rule,
                        idempotency_key=f"event_cancelled_{event_id}_{email}",
                    )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error sending cancellation notifications: {e}")

    @classmethod
    def transition_event_step(
        cls,
        db,
        event_id: str,
        target_step_id: str,
        actor_id: str = "system"
    ) -> Dict[str, Any]:
        """Advance a custom workflow step within an event's workflow configuration."""
        doc_ref = db.collection("events").document(event_id)
        doc = doc_ref.get()
        if not doc.exists:
            return {"success": False, "error": f"Event {event_id} not found"}

        ev_data = doc.to_dict()
        workflow = ev_data.get("workflow_configuration") or ev_data.get("workflow") or []
        updated = False
        for step in workflow:
            if step.get("id") == target_step_id:
                step["status"] = "active"
                updated = True
            elif step.get("status") == "active":
                step["status"] = "completed"

        if updated:
            doc_ref.set({"workflow_configuration": workflow, "updated_at": _utcnow_iso()}, merge=True)
            cls._record_audit_entry(
                db,
                entity_type="event_step",
                entity_id=event_id,
                from_state="previous",
                to_state=target_step_id,
                actor_id=actor_id,
                reason=f"Advanced workflow to step '{target_step_id}'",
                metadata={"step_id": target_step_id}
            )
        return {"success": True, "step_id": target_step_id, "workflow": workflow}


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


# Service Alias
WorkflowService = WorkflowEngine

