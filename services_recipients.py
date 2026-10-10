"""
services_recipients.py — everyone a registration's messages go to (UPG-48).

A team is one registration (UPG-08): the lead plus `members`. Confirmations,
reminders and change and cancellation notices go to each of them who has an
email, once each, keyed by that person's email.
"""


def registration_people(reg: dict):
    """[(email, name, phone)] for the lead and each team member with an email,
    the lead first, each email once (case-insensitive)."""
    reg = reg or {}
    people, seen = [], set()

    def add(email, name, phone):
        email = str(email or '').strip().lower()
        if email and email not in seen:
            seen.add(email)
            people.append((email, name or 'Participant', phone or ''))

    add(reg.get('lead_email') or reg.get('student_email'), reg.get('lead_name') or reg.get('name'),
        reg.get('lead_phone') or reg.get('phone'))
    for m in reg.get('members') or []:
        if isinstance(m, dict):
            add(m.get('email'), m.get('name'), m.get('phone'))
    return people
