"""
services_ledger.py — what one registration earns for the participation ledger (UPG-11).

Credit is worked out from the registration's current attendance, never added
up as scans happen: a registration marked Present earns its event's activity
points and hours once, whether the ticket was scanned once or five times, and
undoing then redoing attendance doesn't credit it twice. The participant's
ledger page and the department export both use this.

An event whose agenda sessions carry hours (an FDP, NSS) credits the hours of
the sessions the registration was scanned into instead of the event's hours
(UPG-159); its points stay the event's.
"""


def credit_for(registration: dict, event: dict, reg_id: str = ''):
    """(points, hours) the registration earns: the event's, once, if it's Present.
    `reg_id` is the registration's document ID, needed for session hours."""
    if str((registration or {}).get('attendance') or '').strip().lower() != 'present':
        return 0.0, 0.0
    event = event or {}
    points = float(event.get('activity_points') or 0.0)
    import services_sessions
    if services_sessions.has_session_hours(event):
        rid = reg_id or (registration or {}).get('reg_id') or ''
        return points, services_sessions.session_hours(str(rid), event)
    return points, float(event.get('activity_hours') or 0.0)
