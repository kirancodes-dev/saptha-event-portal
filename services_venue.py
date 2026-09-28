"""
services_venue.py — Venue Hierarchy, Room Booking & Conflict Detection Engine
=============================================================================

Features:
1. Campus → Building → Room hierarchy management and seeding.
2. VenueBooking (room_id, event_id or session_id, start_time, end_time, status = hold|confirmed|cancelled).
3. Conflict detection:
   - Checks overlapping confirmed bookings on the same room.
   - Touching slots (e.g. 10:00–12:00 and 12:00–14:00) do NOT clash.
   - Cancelled bookings do not block.
   - All times parsed in Asia/Kolkata timezone and stored in UTC.
4. Per-event Google Calendar URL generation and RFC 5545 iCalendar (.ics) exports.
"""

import json
import uuid
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from dateutil.tz import gettz as ZoneInfo

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


class VenueConflictError(Exception):
    """Raised when a room booking conflicts with an existing confirmed booking."""
    pass


# ── Timezone Helpers ─────────────────────────────────────────────────────────

def parse_to_utc(dt_input) -> datetime:
    """
    Parse a datetime string or object into a timezone-aware UTC datetime.
    If naive, assumes Asia/Kolkata timezone.
    """
    if dt_input is None:
        return datetime.now(timezone.utc)
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            dt_input = dt_input.replace(tzinfo=KOLKATA_TZ)
        return dt_input.astimezone(timezone.utc)

    # String input
    from dateutil import parser as dparser
    s = str(dt_input).strip()
    dt = dparser.parse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KOLKATA_TZ)
    return dt.astimezone(timezone.utc)


def format_kolkata(dt_utc) -> str:
    """Format a UTC datetime into human-readable Asia/Kolkata string."""
    if not dt_utc:
        return ""
    if isinstance(dt_utc, str):
        from dateutil import parser as dparser
        dt_utc = dparser.parse(dt_utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    local_dt = dt_utc.astimezone(KOLKATA_TZ)
    return local_dt.strftime("%Y-%m-%d %I:%M %p IST")


def to_utc_iso(dt_input) -> str:
    """Convert input to standard ISO format in UTC."""
    return parse_to_utc(dt_input).isoformat()


# ── Overlap & Conflict Detection ─────────────────────────────────────────────

def slots_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """
    Return True if intervals [start_a, end_a] and [start_b, end_b] overlap.
    Touching slots (start_a == end_b or end_a == start_b) do NOT overlap.
    """
    return start_a < end_b and end_a > start_b


def check_room_conflict(
    db,
    room_id: str,
    start_time,
    end_time,
    exclude_booking_id: Optional[str] = None,
    exclude_event_id: Optional[str] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if an overlapping confirmed booking exists for room_id.

    Returns:
        (True, conflict_details) if a clash exists.
        (False, None) if the slot is clear.
    """
    start_utc = parse_to_utc(start_time)
    end_utc = parse_to_utc(end_time)

    if start_utc > end_utc:
        return True, {
            "reason": "Invalid time interval: start_time must be before end_time."
        }
    if start_utc == end_utc:
        end_utc = start_utc + timedelta(hours=2)

    # Query all confirmed bookings for the room
    bookings_ref = db.collection("venue_bookings").where("room_id", "==", room_id).stream()

    for b in bookings_ref:
        b_data = b.to_dict()
        b_id = b.id

        # Check exclusion
        if exclude_booking_id and str(b_id) == str(exclude_booking_id):
            continue
        b_event_id = b_data.get("event_id") or b_data.get("eventId")
        if exclude_event_id and b_event_id and str(b_event_id) == str(exclude_event_id):
            continue

        # Cancelled bookings don't block
        status = (b_data.get("status") or "confirmed").strip().lower()
        if status == "cancelled":
            continue

        # Touching slots are fine; check confirmed overlap
        if status == "confirmed":
            b_start_raw = b_data.get("start_time") or b_data.get("startTime")
            b_end_raw = b_data.get("end_time") or b_data.get("endTime")
            if not b_start_raw or not b_end_raw:
                continue

            b_start = parse_to_utc(b_start_raw)
            b_end = parse_to_utc(b_end_raw)

            if slots_overlap(start_utc, end_utc, b_start, b_end):
                # Retrieve room and clashing event title
                room_doc = db.collection("rooms").document(room_id).get()
                room_name = room_doc.to_dict().get("name") if room_doc.exists else f"Room {room_id}"

                clashing_title = "Another Event"
                if b_event_id:
                    ev_doc = db.collection("events").document(str(b_event_id)).get()
                    if ev_doc.exists:
                        clashing_title = ev_doc.to_dict().get("title") or "Another Event"
                elif b_data.get("session_id"):
                    clashing_title = f"Session {b_data.get('session_id')}"

                return True, {
                    "booking_id": b_id,
                    "room_id": room_id,
                    "room_name": room_name,
                    "clashing_event_id": str(b_event_id) if b_event_id else None,
                    "clashing_event_title": clashing_title,
                    "start_ist": format_kolkata(b_start),
                    "end_ist": format_kolkata(b_end),
                    "message": (
                        f"Room clash: Room '{room_name}' is already booked for confirmed event "
                        f"'{clashing_title}' from {format_kolkata(b_start)} to {format_kolkata(b_end)}."
                    ),
                }

    return False, None


# ── Booking Management ───────────────────────────────────────────────────────

def create_or_update_venue_booking(
    db,
    *,
    room_id: str,
    start_time,
    end_time,
    event_id: Optional[str] = None,
    session_id: Optional[str] = None,
    status: str = "confirmed",
    notes: str = "",
    booking_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Create or update a room booking, validating conflicts if status is confirmed.
    """
    start_utc = parse_to_utc(start_time)
    end_utc = parse_to_utc(end_time)
    now_iso = datetime.now(timezone.utc).isoformat()
    status_clean = status.strip().lower()

    if status_clean == "confirmed" and not force:
        has_clash, clash_info = check_room_conflict(
            db,
            room_id=room_id,
            start_time=start_utc,
            end_time=end_utc,
            exclude_booking_id=booking_id,
            exclude_event_id=event_id,
        )
        if has_clash and clash_info:
            raise VenueConflictError(clash_info.get("message", "Room booking clash detected."))

    bid = booking_id or f"vb_{uuid.uuid4().hex[:12]}"
    booking_data = {
        "id": bid,
        "room_id": room_id,
        "roomId": room_id,
        "event_id": str(event_id) if event_id else None,
        "eventId": str(event_id) if event_id else None,
        "session_id": session_id,
        "sessionId": session_id,
        "start_time": start_utc.isoformat(),
        "startTime": start_utc.isoformat(),
        "end_time": end_utc.isoformat(),
        "endTime": end_utc.isoformat(),
        "status": status_clean,
        "notes": notes,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    db.collection("venue_bookings").document(bid).set(booking_data)

    # Link room_id to event if provided
    if event_id:
        try:
            ev_ref = db.collection("events").document(str(event_id))
            ev_doc = ev_ref.get()
            if ev_doc.exists:
                ev_ref.update({
                    "room_id": room_id,
                    "roomId": room_id,
                    "start_datetime": start_utc.isoformat(),
                    "startDatetime": start_utc.isoformat(),
                    "end_datetime": end_utc.isoformat(),
                    "endDatetime": end_utc.isoformat(),
                })
        except Exception:
            pass

    return booking_data


# ── Seeding Helper ───────────────────────────────────────────────────────────

def seed_default_venues(db) -> Dict[str, int]:
    """
    Seed standard campus, buildings, and rooms if they do not already exist.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    counts = {"campuses": 0, "buildings": 0, "rooms": 0}

    # 1. Campus
    campus_id = "campus-main"
    campus_doc = db.collection("campuses").document(campus_id).get()
    if not campus_doc.exists:
        db.collection("campuses").document(campus_id).set({
            "id": campus_id,
            "organization_id": "default",
            "name": "Main Campus",
            "slug": "main-campus",
            "address": "Sapthagiri NPS University, Chikkabanavara, Bangalore - 560090",
            "created_at": now_iso,
            "updated_at": now_iso,
        })
        counts["campuses"] += 1

    # 2. Buildings
    buildings = [
        {"id": "bldg-acad-a", "campus_id": campus_id, "name": "Academic Block A", "code": "BLOCK-A"},
        {"id": "bldg-eng", "campus_id": campus_id, "name": "Science & Engineering Block", "code": "BLOCK-ENG"},
        {"id": "bldg-sac", "campus_id": campus_id, "name": "Student Activity Center", "code": "SAC"},
    ]
    for b in buildings:
        doc = db.collection("buildings").document(b["id"]).get()
        if not doc.exists:
            db.collection("buildings").document(b["id"]).set({
                "id": b["id"],
                "campus_id": b["campus_id"],
                "name": b["name"],
                "code": b["code"],
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            counts["buildings"] += 1

    # 3. Rooms
    rooms = [
        {
            "id": "room-auditorium",
            "building_id": "bldg-sac",
            "name": "Main Auditorium",
            "room_number": "AUD-01",
            "capacity": 800,
            "type": "auditorium",
            "facilities": ["Projector", "Sound System", "AC", "Stage Lighting", "Live Stream Setup"],
        },
        {
            "id": "room-seminar-1",
            "building_id": "bldg-acad-a",
            "name": "Seminar Hall 1",
            "room_number": "SH-101",
            "capacity": 150,
            "type": "seminar_hall",
            "facilities": ["Projector", "Sound System", "AC", "Podium"],
        },
        {
            "id": "room-cs-lab-301",
            "building_id": "bldg-eng",
            "name": "CS Lab 301",
            "room_number": "CS-301",
            "capacity": 60,
            "type": "lab",
            "facilities": ["Desktop PCs", "High-speed Internet", "Projector", "AC"],
        },
        {
            "id": "room-mech-workshop",
            "building_id": "bldg-eng",
            "name": "Mech Workshop",
            "room_number": "MW-102",
            "capacity": 40,
            "type": "lab",
            "facilities": ["Toolsets", "Safety Gear", "Workbenches"],
        },
        {
            "id": "room-amphitheatre",
            "building_id": "bldg-sac",
            "name": "Open Amphitheatre",
            "room_number": "OAT-01",
            "capacity": 500,
            "type": "outdoor",
            "facilities": ["Open Air Seating", "PA System", "Spotlights"],
        },
        {
            "id": "room-class-204",
            "building_id": "bldg-acad-a",
            "name": "Classroom 204",
            "room_number": "CR-204",
            "capacity": 70,
            "type": "classroom",
            "facilities": ["Smart Board", "Projector", "Whiteboard"],
        },
    ]

    for r in rooms:
        doc = db.collection("rooms").document(r["id"]).get()
        if not doc.exists:
            db.collection("rooms").document(r["id"]).set({
                "id": r["id"],
                "building_id": r["building_id"],
                "name": r["name"],
                "room_number": r["room_number"],
                "capacity": r["capacity"],
                "type": r["type"],
                "facilities": r["facilities"],
                "facilities_json": json.dumps(r["facilities"]),
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            counts["rooms"] += 1

    return counts


# ── Calendar & Export Helpers ────────────────────────────────────────────────

def get_google_calendar_url(event_data: Dict[str, Any]) -> str:
    """Generate a direct 'Add to Google Calendar' URL."""
    title = event_data.get("title") or event_data.get("name") or "Campus Event"
    desc = event_data.get("description") or ""
    venue = event_data.get("room_name") or event_data.get("venue") or "Sapthagiri NPS University"

    # Resolve timestamps
    start_raw = event_data.get("start_datetime") or event_data.get("date")
    end_raw = event_data.get("end_datetime") or start_raw

    start_dt = parse_to_utc(start_raw) if start_raw else datetime.now(timezone.utc)
    if end_raw and end_raw != start_raw:
        end_dt = parse_to_utc(end_raw)
    else:
        # Default 2-hour event duration
        from datetime import timedelta
        end_dt = start_dt + timedelta(hours=2)

    fmt_start = start_dt.strftime("%Y%m%dT%H%M%SZ")
    fmt_end = end_dt.strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{fmt_start}/{fmt_end}",
        "details": desc[:500],
        "location": venue,
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def generate_event_ics(event_data: Dict[str, Any]) -> str:
    """Generate RFC 5545 iCalendar format for a single event."""
    title = (event_data.get("title") or event_data.get("name") or "Campus Event").replace("\n", " ")
    desc = (event_data.get("description") or "").replace("\n", " ")
    venue = (event_data.get("room_name") or event_data.get("venue") or "Sapthagiri NPS University").replace("\n", " ")
    ev_id = event_data.get("id") or "event"

    start_raw = event_data.get("start_datetime") or event_data.get("date")
    end_raw = event_data.get("end_datetime") or start_raw

    start_dt = parse_to_utc(start_raw) if start_raw else datetime.now(timezone.utc)
    if end_raw and end_raw != start_raw:
        end_dt = parse_to_utc(end_raw)
    else:
        from datetime import timedelta
        end_dt = start_dt + timedelta(hours=2)

    dt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dt_start = start_dt.strftime("%Y%m%dT%H%M%SZ")
    dt_end = end_dt.strftime("%Y%m%dT%H%M%SZ")
    uid = f"event-{ev_id}@events.snpsu.edu.in"

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//SapthaEvent//Universal Event OS//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dt_stamp}\r\n"
        f"DTSTART:{dt_start}\r\n"
        f"DTEND:{dt_end}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        f"LOCATION:{venue}\r\n"
        "STATUS:CONFIRMED\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics


def generate_calendar_feed_ics(events_list: List[Dict[str, Any]], calendar_name: str = "My Campus Events") -> str:
    """Generate an RFC 5545 personal calendar feed for multiple events."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SapthaEvent//Personal Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{calendar_name}",
        "X-WR-TIMEZONE:Asia/Kolkata",
    ]
    dt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for ev in events_list:
        title = (ev.get("title") or ev.get("name") or "Event").replace("\n", " ")
        desc = (ev.get("description") or "").replace("\n", " ")
        venue = (ev.get("room_name") or ev.get("venue") or "Sapthagiri NPS University").replace("\n", " ")
        ev_id = ev.get("id") or uuid.uuid4().hex[:8]

        start_raw = ev.get("start_datetime") or ev.get("date")
        end_raw = ev.get("end_datetime") or start_raw
        start_dt = parse_to_utc(start_raw) if start_raw else datetime.now(timezone.utc)
        if end_raw and end_raw != start_raw:
            end_dt = parse_to_utc(end_raw)
        else:
            from datetime import timedelta
            end_dt = start_dt + timedelta(hours=2)

        dt_start = start_dt.strftime("%Y%m%dT%H%M%SZ")
        dt_end = end_dt.strftime("%Y%m%dT%H%M%SZ")
        uid = f"feed-{ev_id}@events.snpsu.edu.in"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dt_stamp}",
            f"DTSTART:{dt_start}",
            f"DTEND:{dt_end}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{venue}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR\r\n")
    return "\r\n".join(lines)


# ── Change Notification Trigger ──────────────────────────────────────────────

def notify_event_details_changed(
    db,
    *,
    event_id: str,
    previous_data: Dict[str, Any],
    new_data: Dict[str, Any],
) -> int:
    """
    Checks if an event's venue, room, date, or time has changed.
    If so, notifies all registered participants through services_automation / routes_notifications_v2
    exactly once per participant.

    Returns the number of participants notified.
    """
    if not previous_data or not new_data:
        return 0

    prev_venue = str(previous_data.get("venue") or "").strip()
    new_venue = str(new_data.get("venue") or "").strip()
    prev_room = str(previous_data.get("room_id") or previous_data.get("roomId") or "").strip()
    new_room = str(new_data.get("room_id") or new_data.get("roomId") or "").strip()
    prev_date = str(previous_data.get("date") or "").strip()
    new_date = str(new_data.get("date") or "").strip()
    prev_time = str(previous_data.get("time") or "").strip()
    new_time = str(new_data.get("time") or "").strip()
    prev_start = str(previous_data.get("start_datetime") or previous_data.get("startDatetime") or "").strip()
    new_start = str(new_data.get("start_datetime") or new_data.get("startDatetime") or "").strip()

    venue_changed = (new_venue and new_venue != prev_venue) or (new_room and new_room != prev_room)
    time_changed = (new_date and new_date != prev_date) or (new_time and new_time != prev_time) or (new_start and new_start != prev_start)

    if not venue_changed and not time_changed:
        return 0

    # Determine display info
    event_title = new_data.get("title") or previous_data.get("title") or "Event"
    display_venue = new_data.get("room_name") or new_data.get("venue") or prev_venue or "Campus"
    display_time = new_data.get("date") or new_data.get("start_datetime") or prev_date or "Scheduled Date"

    changes = []
    if venue_changed:
        changes.append(f"Venue updated to '{display_venue}'")
    if time_changed:
        changes.append(f"Date/Time updated to '{display_time}'")
    change_summary = "; ".join(changes)

    try:
        from services_automation import NotificationAutomationEngine
        regs = list(db.collection("registrations").where("event_id", "==", str(event_id)).stream())
        notified_emails = set()
        count = 0

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
                    "venue_name": display_venue,
                    "start_time": display_time,
                }
                custom_rule = {
                    "title": f"Update: {event_title}",
                    "message": f"Hello {recipient_name}, important schedule change for '{event_title}': {change_summary}.",
                    "notif_type": "event_reminder",
                    "channels": ["in_app", "email"],
                }
                idempotency_key = f"event_change_{event_id}_{email}_{abs(hash(change_summary))}"
                NotificationAutomationEngine.dispatch_trigger(
                    db,
                    trigger_name="on_event_details_changed",
                    context=context,
                    custom_rule=custom_rule,
                    idempotency_key=idempotency_key,
                )
                count += 1
        return count
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to notify participants of event change: {e}")
        return 0

