"""
services_recipients.py — everyone a registration's messages go to (UPG-48).

A team is one registration (UPG-08): the lead plus `members`. Confirmations,
reminders and change and cancellation notices go to each of them who has an
email, once each, keyed by that person's email, when NOTIFY_TEAM_MEMBERS is
on. By default only the team lead gets them, to stay within the free email
quota (UPG-152, owner 2026-10-31).
"""


def notify_team_members() -> bool:
    import os
    try:
        from flask import current_app
        return bool(current_app.config.get('NOTIFY_TEAM_MEMBERS', False))
    except RuntimeError:   # outside an app context (a worker without one)
        return os.environ.get('NOTIFY_TEAM_MEMBERS', 'false').strip().lower() in ('1', 'true', 'yes')


def registration_people(reg: dict, everyone=None):
    """[(email, name, phone)] for the lead and, when team members are
    notified, each team member with an email: the lead first, each email
    once (case-insensitive). `everyone` overrides NOTIFY_TEAM_MEMBERS."""
    reg = reg or {}
    people, seen = [], set()

    def add(email, name, phone):
        email = str(email or '').strip().lower()
        if email and email not in seen:
            seen.add(email)
            people.append((email, name or 'Participant', phone or ''))

    add(reg.get('lead_email') or reg.get('student_email'), reg.get('lead_name') or reg.get('name'),
        reg.get('lead_phone') or reg.get('phone'))
    if notify_team_members() if everyone is None else everyone:
        for m in reg.get('members') or []:
            if isinstance(m, dict):
                add(m.get('email'), m.get('name'), m.get('phone'))
    return people
