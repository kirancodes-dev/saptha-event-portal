"""
routes_teams.py — Team formation for group events

Students can create a team (gets a 6-char join code) and share the code
with teammates. Teammates use /teams/join to enter the code and be added.

Firestore collection: teams
  { team_id, event_id, team_name, lead_email, lead_name,
    members: [{email,name,usn,phone}], join_code, max_size, status, created_at }
"""
import datetime
import secrets
import string

from flask import (Blueprint, flash, redirect, render_template, request,
                   session)
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db
from utils import login_required, role_required, log_action, safe_int

teams_bp = Blueprint('teams', __name__, url_prefix='/teams')


def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _new_join_code():
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(6))


def _get_user(email):
    if not email:
        return {}
    doc = db.collection('users').document(email).get()
    return doc.to_dict() if doc.exists else {}


# ──────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────
@teams_bp.route('/create/<event_id>', methods=['GET', 'POST'])
@login_required
@role_required('Student')
def create_team(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/participant/dashboard')
    event = event_doc.to_dict()

    if request.method == 'POST':
        team_name = (request.form.get('team_name') or '').strip()
        max_size  = safe_int(request.form.get('max_size') or event.get('max_team_size', 4))
        if not team_name:
            flash("Team name is required.", "warning")
            return redirect(f'/teams/create/{event_id}')
        if max_size < 2 or max_size > 10:
            max_size = 4

        lead_email = session.get('user_id')
        lead_user  = _get_user(lead_email)

        # One active team per event per lead
        existing = list(
            db.collection('teams')
              .where(filter=_ff('event_id', '==', event_id))
              .where(filter=_ff('lead_email', '==', lead_email))
              .limit(1).stream()
        )
        if existing:
            flash("You already have a team for this event.", "warning")
            return redirect(f'/teams/{existing[0].id}')

        # Retry on code collision (tiny chance)
        for _ in range(5):
            code = _new_join_code()
            dup = list(
                db.collection('teams')
                  .where(filter=_ff('join_code', '==', code))
                  .limit(1).stream()
            )
            if not dup:
                break

        team_id = f"TEAM-{int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)}"
        db.collection('teams').document(team_id).set({
            'team_id':    team_id,
            'event_id':   event_id,
            'event_title': event.get('title', ''),
            'team_name':  team_name,
            'lead_email': lead_email,
            'lead_name':  lead_user.get('name', session.get('name', '')),
            'members': [{
                'email': lead_email,
                'name':  lead_user.get('name', session.get('name', '')),
                'usn':   lead_user.get('usn', ''),
                'phone': lead_user.get('phone', ''),
                'role':  'Leader',
            }],
            'join_code':   code,
            'max_size':    max_size,
            'status':      'Open',
            'created_at':  datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        log_action(lead_email, 'team_create', f"{team_id} for {event_id}")
        flash(f"Team created. Share code {code} with your teammates.", "success")
        return redirect(f'/teams/{team_id}')

    return render_template(
        'teams/create.html',
        event=event, event_id=event_id,
        default_max=event.get('max_team_size', 4),
    )


# ──────────────────────────────────────────
# JOIN
# ──────────────────────────────────────────
@teams_bp.route('/join', methods=['GET', 'POST'])
@login_required
@role_required('Student')
def join_team():
    if request.method == 'POST':
        code = (request.form.get('join_code') or '').strip().upper()
        if len(code) != 6:
            flash("Enter a valid 6-character code.", "warning")
            return redirect('/teams/join')

        matches = list(
            db.collection('teams')
              .where(filter=_ff('join_code', '==', code))
              .limit(1).stream()
        )
        if not matches:
            flash("Team not found.", "danger")
            return redirect('/teams/join')

        team_doc = matches[0]
        team = team_doc.to_dict() or {}

        if team.get('status') != 'Open':
            flash("This team is no longer accepting members.", "warning")
            return redirect('/teams/join')

        email   = session.get('user_id') or ''
        members = team.get('members', [])

        if any((m.get('email') or '').lower() == email.lower() for m in members):
            flash("You're already on this team.", "info")
            return redirect(f'/teams/{team_doc.id}')

        max_size = safe_int(team.get('max_size', 4))
        if len(members) >= max_size:
            flash("This team is already full.", "warning")
            return redirect('/teams/join')

        user    = _get_user(email)
        members.append({
            'email': email,
            'name':  user.get('name', session.get('name', '')),
            'usn':   user.get('usn', ''),
            'phone': user.get('phone', ''),
            'role':  'Member',
        })

        db.collection('teams').document(team_doc.id).update({
            'members': members,
            'status':  'Full' if len(members) >= max_size else 'Open',
        })
        log_action(email, 'team_join', team_doc.id)
        flash(f"Joined team {team.get('team_name')}.", "success")
        return redirect(f'/teams/{team_doc.id}')

    return render_template('teams/join.html')


# ──────────────────────────────────────────
# VIEW
# ──────────────────────────────────────────
@teams_bp.route('/<team_id>')
@login_required
@role_required('Student')
def view_team(team_id):
    doc = db.collection('teams').document(team_id).get()
    if not doc.exists:
        flash("Team not found.", "danger")
        return redirect('/participant/dashboard')
    team = doc.to_dict() or {}
    team['team_id'] = doc.id

    # Enrich with live event title
    event_id = team.get('event_id')
    if event_id:
        event_doc = db.collection('events').document(event_id).get()
        if event_doc.exists:
            evt = event_doc.to_dict()
            team['event_title'] = evt.get('title', team.get('event_title', ''))

    email = session.get('user_id')
    is_member = any((m.get('email') or '').lower() == (email or '').lower()
                    for m in team.get('members', []))
    if not is_member:
        flash("You don't have access to this team.", "warning")
        return redirect('/participant/dashboard')

    is_leader = team.get('lead_email', '').lower() == (email or '').lower()
    return render_template('teams/view.html',
                           team=team, is_leader=is_leader)


# ──────────────────────────────────────────
# LEAVE
# ──────────────────────────────────────────
@teams_bp.route('/<team_id>/leave', methods=['POST'])
@login_required
@role_required('Student')
def leave_team(team_id):
    ref = db.collection('teams').document(team_id)
    doc = ref.get()
    if not doc.exists:
        flash("Team not found.", "warning")
        return redirect('/participant/dashboard')

    team  = doc.to_dict() or {}
    email = session.get('user_id') or ''

    if team.get('lead_email', '').lower() == email.lower():
        # Leader leaving = disband team
        ref.delete()
        log_action(email, 'team_disband', team_id)
        flash("Team disbanded.", "info")
        return redirect('/participant/dashboard')

    new_members = [m for m in team.get('members', [])
                   if (m.get('email') or '').lower() != email.lower()]
    ref.update({'members': new_members, 'status': 'Open'})
    log_action(email, 'team_leave', team_id)
    flash("You left the team.", "info")
    return redirect('/participant/dashboard')


# ──────────────────────────────────────────
# CLOSE (leader locks roster before registration)
# ──────────────────────────────────────────
@teams_bp.route('/<team_id>/close', methods=['POST'])
@login_required
@role_required('Student')
def close_team(team_id):
    ref = db.collection('teams').document(team_id)
    doc = ref.get()
    if not doc.exists:
        flash("Team not found.", "warning")
        return redirect('/participant/dashboard')
    team  = doc.to_dict() or {}
    email = session.get('user_id') or ''
    if team.get('lead_email', '').lower() != email.lower():
        flash("Only the team leader can close the team.", "danger")
        return redirect(f'/teams/{team_id}')
    ref.update({'status': 'Closed'})
    flash("Team roster locked.", "success")
    return redirect(f'/teams/{team_id}')
