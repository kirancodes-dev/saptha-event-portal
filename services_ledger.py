"""
services_ledger.py — what one registration earns for the participation ledger (UPG-11).

Credit is worked out from the registration's current attendance, never added
up as scans happen: a registration marked Present earns its event's activity
points and hours once, whether the ticket was scanned once or five times, and
undoing then redoing attendance doesn't credit it twice. The participant's
ledger page and the department export both use this.
"""


def credit_for(registration: dict, event: dict):
    """(points, hours) the registration earns: the event's, once, if it's Present."""
    if str((registration or {}).get('attendance') or '').strip().lower() != 'present':
        return 0.0, 0.0
    event = event or {}
    return float(event.get('activity_points') or 0.0), float(event.get('activity_hours') or 0.0)
