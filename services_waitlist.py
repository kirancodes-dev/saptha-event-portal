"""
services_waitlist.py — a waitlist's order and each person's place in it (UPG-114).

The order is the order people joined (`joined_at`, then the entry's id when two
joined in the same instant). A person's place is worked out when it's shown:
one more than the number of people still waiting who joined earlier. So places
never repeat, and they close up when someone ahead is promoted or leaves. The
`position` stored on an entry is only its place on the day it joined.
"""


def waiting(db, event_id: str) -> list:
    """[(entry id, entry)] still waiting for the event, first in line first."""
    query = db.collection('waitlists').where('event_id', '==', event_id).where('status', '==', 'waiting')
    entries = [(d.id, d.to_dict() or {}) for d in query.stream()]
    return sorted(entries, key=lambda e: (str(e[1].get('joined_at') or ''), str(e[0])))


def place_in_line(db, event_id: str, email: str):
    """This person's place (1 = next to be promoted), or None if they aren't waiting."""
    email = (email or '').strip().lower()
    for place, (_, entry) in enumerate(waiting(db, event_id), start=1):
        if str(entry.get('user_email') or entry.get('email') or '').strip().lower() == email:
            return place
    return None
