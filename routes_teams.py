"""
routes_teams.py — teams live on the registration itself (UPG-08)

The lead registers the team through the event's form (team name and the
members they already have). The registration carries a 6-character invite
code; anyone else joins with it, which adds them to the registration's
`members`, so tickets, check-in and judging see them. Team size stays within
the event's limits. The lead can remove a member and replace the code.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, session

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


def _add_member(reg_id, member, team_max):
    """Add one member atomically: 'added', 'already' or 'full' (UPG-52).

    On the SQL layer the registration row is locked (SELECT ... FOR UPDATE on
    PostgreSQL) while its member rows are counted and the new one inserted, so
    two people joining at once can neither overwrite each other nor push the
    team past team_max. Firestore mode (legacy) keeps the read-then-write."""
    from db_adapter import SQLFirestoreAdapter
    if not isinstance(db, SQLFirestoreAdapter):
        doc = db.collection('registrations').document(reg_id).get()
        members = list((doc.to_dict() or {}).get('members') or [])
        if any(_email(m) == _email(member) for m in members):
            return 'already'
        if len(members) >= team_max:
            return 'full'
        _save_members(reg_id, members + [member])
        return 'added'

    import json
    import uuid
    from sqlalchemy.orm import Session
    from db_adapter import to_uuid
    from db_pg import get_engine
    from models_pg import Registration, TeamMember
    with Session(get_engine()) as s, s.begin():
        reg = (s.query(Registration).filter(Registration.id == to_uuid(reg_id))
                .with_for_update().one_or_none())
        if reg is None:
            return 'full'
        rows = s.query(TeamMember).filter(TeamMember.registration_id == reg.id).all()
        if any((r.email or '').strip().lower() == _email(member) for r in rows):
            return 'already'
        if len(rows) >= team_max:
            return 'full'
        s.add(TeamMember(id=uuid.uuid4(), registration_id=reg.id, name=member.get('name') or 'Unknown',
                         email=member.get('email', ''), phone=member.get('phone', ''),
                         usn=member.get('usn', ''), extra_json=json.dumps(member)))
        count = len(rows) + 1
    db.collection('registrations').document(reg_id).update({'member_count': count})
    return 'added'


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
    # Signed in to join, so already confirmed (UPG-207)
    import datetime
    member = {'role': 'Member', 'email': me, 'name': profile.get('name') or session.get('name', ''),
              'usn': (profile.get('usn') or '').upper(), 'phone': profile.get('phone', ''),
              'confirmed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'confirmed_by': 'invite'}
    # The checks above are re-made atomically while adding (UPG-52)
    added = _add_member(reg_id, member, team_max)
    if added == 'full':
        flash(f"This team is full ({team_max} people).", "warning")
        return redirect('/teams/join')
    if added == 'already':
        flash("You're already on this team.", "info")
        return redirect(f'/teams/{reg_id}')
    log_action(db, "TEAM_JOIN", f"{me} joined {reg.get('team_name')} ({reg_id})")
    # The new member's confirmation, once: a repeat join stops at 'already'
    # above (UPG-48). Only when team members get emails (UPG-152); the page
    # below confirms the join either way.
    from services_recipients import notify_team_members
    import services_hackathon   # none for a portal-only event (UPG-195)
    if notify_team_members() and services_hackathon.email_allowed(event, 'team'):
        try:
            from utils_email import send_registration_confirmed_email
            send_registration_confirmed_email(
                me, member['name'] or 'Participant', event.get('title', ''),
                event_date=event.get('date', ''), venue=event.get('venue', ''),
                added_by=reg.get('lead_name') or 'Your team lead', team_name=reg.get('team_name', ''))
        except Exception:
            pass
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
    import services_team_confirm as confirm
    statuses = {_email(m): confirm.status(m) for m in confirm.others(reg)} if confirm.enabled(event or {}) else {}
    resends = {_email(m): confirm.resends_left(m) for m in confirm.others(reg)}
    import services_registration_edit   # the lead corrects the details (UPG-225)
    may_edit = _is_lead(reg) and not services_registration_edit.lead_may_edit(reg, event or {})
    # The lead adds members up to the limit, or is told why not (UPG-241)
    import services_hackathon
    import services_team_members
    add_block = services_team_members.why_not(reg, event or {}) if _is_lead(reg) else ''
    return render_template('teams/view.html', reg=reg, reg_id=reg_id, event=event, is_lead=_is_lead(reg),
                           team_min=team_min, team_max=team_max, statuses=statuses, resends=resends,
                           may_edit=may_edit, add_block=add_block,
                           room_left=services_team_members.room_left(reg, team_max),
                           confirm_on=confirm.enabled(event or {}) and services_hackathon.email_allowed(
                               event or {}, 'member_confirm'))


# ── Members confirm their email (UPG-207) ──────────────────────────────────

def _lead_team(reg_id):
    """(registration, event) when the signed-in person leads this team; 403 otherwise."""
    reg, event = _team(reg_id)
    if reg is None or not _is_lead(reg):
        abort(403)
    return reg, event


@teams_bp.route('/<reg_id>/members/resend', methods=['POST'])
@login_required
def resend_confirmation(reg_id):
    import services_team_confirm as confirm
    reg, event = _lead_team(reg_id)
    email = (request.form.get('email') or '').strip().lower()
    try:
        outcome = confirm.resend(db, reg_id, reg, event, email, by=_me())
    except confirm.ConfirmError as exc:
        flash(str(exc), 'warning')
        return redirect(f'/teams/{reg_id}')
    flash({'sent': f"A new link was sent to {email}; the earlier one no longer works.",
           'limit': "Today's email limit is reached, so nothing was sent. Try again tomorrow.",
           }.get(outcome, f"The email to {email} couldn't be sent. Try again later."),
          'success' if outcome == 'sent' else 'warning')
    return redirect(f'/teams/{reg_id}')


@teams_bp.route('/<reg_id>/members/email', methods=['POST'])
@login_required
def correct_member_email(reg_id):
    import services_team_confirm as confirm
    reg, event = _lead_team(reg_id)
    old = (request.form.get('email') or '').strip().lower()
    new = (request.form.get('new_email') or '').strip().lower()
    try:
        outcome = confirm.correct_email(db, reg_id, reg, event, old, new, by=_me())
    except confirm.ConfirmError as exc:
        flash(str(exc), 'warning')
        return redirect(f'/teams/{reg_id}')
    flash(f"Email changed to {new}. " + ({'sent': "A link was sent there; the old one no longer works.",
                                         'limit': "Today's email limit is reached: resend the link tomorrow."}
                                        .get(outcome, "The email couldn't be sent: resend the link later.")),
          'success' if outcome == 'sent' else 'warning')
    return redirect(f'/teams/{reg_id}')


@teams_bp.route('/confirm/<token>', methods=['GET', 'POST'])
def confirm_member(token):
    """A member's emailed link: choose a password (a new account), or sign
    in (an existing one), and the member is confirmed."""
    import services_team_confirm as confirm
    from services_accounts import is_safe_next
    reg_id, reg, member, error = confirm.load_token(db, token)
    if error:
        flash({'expired': "This link has expired: it works for 48 hours. Ask your team lead to resend it.",
               'replaced': "This link no longer works: a newer one was sent, or your team lead changed the email. "
                           "Use the latest email, or ask your team lead."}
              .get(error, "This link isn't valid."), 'danger')
        return redirect('/login')
    email = _email(member)
    if member.get('confirmed_at'):
        flash("You've already confirmed. Log in to see your team.", 'info')
        return redirect(f'/teams/{reg_id}' if _me() == email else '/login')
    doc = db.collection('users').document(email).get()
    user = (doc.to_dict() or {}) if doc.exists else {}
    if not user:
        flash("This link isn't valid.", 'danger')
        return redirect('/login')

    if not user.get('needs_password_reset'):
        # An account with a password: confirm by signing in as it
        if _me() == email:
            confirm.confirm(db, reg_id, email, 'sign-in')
            flash(f"Confirmed: you're on team {reg.get('team_name') or ''}.", 'success')
            return redirect(f'/teams/{reg_id}')
        if _me():
            flash(f"This link is for {email}. Log out, then open it again.", 'warning')
            return redirect('/participant/dashboard')
        target = f'/teams/confirm/{token}'
        flash(f"Log in as {email} to confirm your place in the team.", 'info')
        return redirect('/login?next=' + target if is_safe_next(target) else '/login')

    if request.method == 'POST':
        from werkzeug.security import generate_password_hash

        from routes_auth import _login_role, _set_session
        from utils import validate_password_strength
        new_pw = request.form.get('new_password', '')
        ok, pw_err = validate_password_strength(new_pw)
        if new_pw != request.form.get('confirm_password', ''):
            flash("Passwords do not match.", 'danger')
            return redirect(request.path)
        if not ok:
            flash(pw_err, 'danger')
            return redirect(request.path)
        db.collection('users').document(email).update({
            'password': generate_password_hash(new_pw, method='pbkdf2:sha256'),
            'needs_password_reset': False, 'email_verified': True})
        confirm.confirm(db, reg_id, email, 'link')
        category = user.get('category', 'General')
        _set_session(email, user.get('name', 'Participant'), _login_role(user.get('role', 'Student')) or 'Student',
                     str(getattr(category, 'value', category)), remember_me=False)
        flash(f"Confirmed and your password is set. Next time, log in with {email}.", 'success')
        return redirect(f'/teams/{reg_id}')
    return render_template('reset_password_token.html', email=email, name=member.get('name') or user.get('name'),
                           heading='Confirm your team place',
                           intro=f"{reg.get('lead_name') or 'Your team lead'} added you to team "
                                 f"{reg.get('team_name') or ''} for {reg.get('event_title') or 'an event'}. "
                                 "Choose a password to confirm; you'll sign in with this email:",
                           button='Confirm and set password')


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


@teams_bp.route('/<reg_id>/members/add', methods=['POST'])
@login_required
def add_member(reg_id):
    """The lead adds a member, up to the team's limit (UPG-241)."""
    import services_team_members as tm
    from routes_forms import team_limits
    reg, event = _lead_team(reg_id)
    try:
        member, told = tm.add(db, reg_id, reg, event or {}, request.form, by=_me())
    except tm.AddError as exc:
        flash(str(exc), 'warning')
        return redirect(f'/teams/{reg_id}#add-member')
    log_action(db, "TEAM_MEMBER_ADDED", f"{_me()} added {member['email']} to {reg.get('team_name')} ({reg_id})")
    fresh, _ = _team(reg_id)
    count = len((fresh or {}).get('members') or [])
    _, team_max = team_limits(event or {})
    flash(f"{member['name']} is added. Your team now has {count} of {team_max}. " + {
        'link': f"An email went to {member['email']} to confirm and set a password.",
        'limit': "Today's email limit is reached, so their link wasn't sent: resend it tomorrow.",
        'failed': "Their email couldn't be sent: use Resend link below.",
        'email': f"An email telling them went to {member['email']}.",
    }.get(told, "They see the team when they sign in with that email."), 'success')
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
