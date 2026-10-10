"""
services_participants.py — who takes part: students, faculty, external (UPG-12).

Every registration and account has a participant_type. The event decides who
may register (`allowed_participants`); FDPs are usually faculty only and
conferences faculty and external participants. An event that doesn't say
takes students only, as every event did before.

Faculty and external participants use the same participant dashboard, ticket,
check-in and feedback as students (their account role stays the participant
role); the type tells them apart in registrations, exports and analytics.
"""
PARTICIPANT_TYPES = ('student', 'faculty', 'external')
LABELS = {'student': 'Student', 'faculty': 'Faculty', 'external': 'External participant'}
PLURALS = {'student': 'students', 'faculty': 'faculty', 'external': 'external participants'}
NEEDS_AFFILIATION = ('faculty', 'external')   # these give designation and institution


def allowed_types(event: dict) -> list:
    """The participant types an event takes, in a fixed order; students by default."""
    raw = (event or {}).get('allowed_participants') or ['student']
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.split(',')]
    allowed = [p for p in PARTICIPANT_TYPES if p in {str(x).strip().lower() for x in raw}]
    return allowed or ['student']


def from_form(values) -> list:
    """The 'who can register' checkboxes of the create and edit forms."""
    picked = [p for p in PARTICIPANT_TYPES if p in values]
    return picked or ['student']


def type_of(record: dict) -> str:
    """A registration's or account's participant type; older ones are students."""
    t = str((record or {}).get('participant_type') or '').strip().lower()
    return t if t in PARTICIPANT_TYPES else 'student'
