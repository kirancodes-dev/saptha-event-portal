"""
routes_teams.py — teams live on the registration itself (UPG-08)

The lead registers the team through the event's form (team name and the
members they already have). The registration carries a 6-character invite
code; anyone else joins with it, which adds them to the registration's
`members`, so tickets, check-in and judging see them. Team size stays within
the event's limits. The lead can remove a member and replace the code.
"""
from flask import Blueprint, flash, redirect, render_template, request, session

from models import db
from utils import login_required, role_required, log_action

teams_bp = Blueprint('teams', __name__, url_prefix='/teams')


def _me():
    return (session.get('user_id') or '').strip().lower()


def _email(member):
    return (member.get('email') or '').strip().lower()


def _team(reg_id):
    """(registration, event) for a team registration, else (None, None)."""
    doc = db.collection('registrations').document(reg_id).get()
    if not doc.exists:
        return None, None
    reg = doc.to_dict() or {}
    if not reg.get('team_code'):
        return None, None
    ev = db.collection('events').document(str(reg.get('event_id', ''))).get()
    return reg, ((ev.to_dict() or {}) if ev.exists else {})


def _is_lead(reg):
    return (reg.get('lead_email') or '').lower() == _me()


def _registered_for(event_id, email):
    """Whether email already leads or belongs to a registration for the event."""
    for d in db.collection('registrations').where('event_id', '==', event_id).stream():
        r = d.to_dict() or {}
        if (r.get('lead_email') or '').lower() == email or any(_email(m) == email for m in r.get('members') or []):
            return True
    return False


def _save_members(reg_id, members):
    db.collection('registrations').document(reg_id).update({'members': members, 'member_count': len(members)})


@teams_bp.route('/create/<event_id>', methods=['GET', 'POST'])
def create_team(event_id):
    """A team is created by registering it through the event's form."""
    return redirect(f'/forms/register/{event_id}')


@teams_bp.route('/join', methods=['GET', 'POST'])
@login_required
@role_required('Student')
def join_team():
    from routes_forms import registration_closed, team_limits
    if request.method == 'GET':
        return render_template('teams/join.html', code=(request.args.get('code') or '').strip().upper())

    code = (request.form.get('join_code') or '').strip().upper()
    found = list(db.collection('registrations').where('team_code', '==', code).limit(1).stream()) if len(code) == 6 else []
    if not found:
        flash("No team has that code. Check it with your team lead.", "warning")
        return redirect('/teams/join')
    reg_id, reg = found[0].id, found[0].to_dict() or {}
    event_id = str(reg.get('event_id', ''))
    ev_doc = db.collection('events').document(event_id).get()
    event = (ev_doc.to_dict() or {}) if ev_doc.exists else {}
    me = _me()
    members = list(reg.get('members') or [])

    if any(_email(m) == me for m in members) or (reg.get('lead_email') or '').lower() == me:
        flash("You're already on this team.", "info")
        return redirect(f'/teams/{reg_id}')
    if not event or registration_closed(event):
        flash("This event isn't taking registrations, so its teams can't change.", "warning")
        return redirect('/teams/join')
    if _registered_for(event_id, me):
        flash("You're already registered for this event with another team.", "warning")
        return redirect('/teams/join')
    _, team_max = team_limits(event)
    if len(members) >= team_max:
        flash(f"This team is full ({team_max} people).", "warning")
        return redirect('/teams/join')

    profile_doc = db.collection('users').document(me).get()
    profile = (profile_doc.to_dict() or {}) if profile_doc.exists else {}
    members.append({'role': 'Member', 'email': me, 'name': profile.get('name') or session.get('name', ''),
                    'usn': (profile.get('usn') or '').upper(), 'phone': profile.get('phone', '')})
    _save_members(reg_id, members)
    log_action(db, "TEAM_JOIN", f"{me} joined {reg.get('team_name')} ({reg_id})")
    flash(f"You joined {reg.get('team_name')}. Your ticket is on the team page.", "success")
    return redirect(f'/teams/{reg_id}')


@teams_bp.route('/<reg_id>')
@login_required
def view_team(reg_id):
    from routes_forms import team_limits
    reg, event = _team(reg_id)
    if reg is None or not (_is_lead(reg) or any(_email(m) == _me() for m in reg.get('members') or [])):
        flash("You don't have access to this team.", "warning")
        return redirect('/participant/dashboard')
    team_min, team_max = team_limits(event or {})
    return render_template('teams/view.html', reg=reg, reg_id=reg_id, event=event, is_lead=_is_lead(reg),
                           team_min=team_min, team_max=team_max)


@teams_bp.route('/<reg_id>/remove', methods=['POST'])
@login_required
def remove_member(reg_id):
    from routes_forms import team_limits
    reg, event = _team(reg_id)
    if reg is None or not _is_lead(reg):
        flash("Only the team lead can remove members.", "danger")
        return redirect(f'/teams/{reg_id}' if reg else '/participant/dashboard')
    email = (request.form.get('email') or '').strip().lower()
    members = list(reg.get('members') or [])
    kept = [m for m in members if _email(m) != email or m.get('role') == 'Lead']
    if not email or len(kept) == len(members):
        flash("That person isn't a member of this team.", "warning")
        return redirect(f'/teams/{reg_id}')
    _save_members(reg_id, kept)
    log_action(db, "TEAM_REMOVE", f"{_me()} removed {email} from {reg_id}")
    team_min, _ = team_limits(event or {})
    flash(f"{email} removed from the team." + (
        f" Your team now has {len(kept)}; it needs {team_min} to take part." if len(kept) < team_min else ''),
        "success" if len(kept) >= team_min else "warning")
    return redirect(f'/teams/{reg_id}')


@teams_bp.route('/<reg_id>/regenerate', methods=['POST'])
@login_required
def regenerate_code(reg_id):
    from routes_forms import new_team_code
    reg, _ = _team(reg_id)
    if reg is None or not _is_lead(reg):
        flash("Only the team lead can change the invite code.", "danger")
        return redirect(f'/teams/{reg_id}' if reg else '/participant/dashboard')
    db.collection('registrations').document(reg_id).update({'team_code': new_team_code(db)})
    log_action(db, "TEAM_CODE_RESET", f"{_me()} replaced the invite code of {reg_id}")
    flash("New invite code made; the old one no longer works.", "success")
    return redirect(f'/teams/{reg_id}')


@teams_bp.route('/<reg_id>/leave', methods=['POST'])
@login_required
def leave_team(reg_id):
    reg, _ = _team(reg_id)
    me = _me()
    if reg is None or _is_lead(reg) or not any(_email(m) == me for m in reg.get('members') or []):
        flash("You can't leave this team." if reg else "Team not found.", "warning")
        return redirect('/participant/dashboard')
    _save_members(reg_id, [m for m in reg.get('members') or [] if _email(m) != me])
    log_action(db, "TEAM_LEAVE", f"{me} left {reg_id}")
    flash("You left the team.", "info")
    return redirect('/participant/dashboard')
