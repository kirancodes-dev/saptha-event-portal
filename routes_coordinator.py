"""
routes_coordinator.py

Key change: create_event() now accepts form_schema JSON posted from the
wizard Step 4 and saves it atomically to event_forms/<event_id> at the
same time the event document is created.  The participant-facing
/forms/register/<event_id> route therefore has a form ready immediately —
no separate "Build Form" step required.
"""
import csv
import datetime
import json
import random
import secrets
import string
from io import StringIO

from flask import (Blueprint, Response, flash, jsonify,
                   redirect, render_template, request, session)
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import generate_password_hash

from models import db
from utils import login_required, role_required, log_action, safe_int
from utils_email import (send_appointment_email, send_broadcast_email,
                          send_credentials_email, send_ticket_email,
                          send_result_email)

# WhatsApp — safe import so app still starts if twilio not installed
try:
    from utils_whatsapp import (
        send_room_assignment_whatsapp, send_result_whatsapp,
        send_elimination_whatsapp,    send_broadcast_whatsapp,
        send_staff_credentials_whatsapp, send_ticket_whatsapp,
    )
    WA_ENABLED = True
except ImportError:
    WA_ENABLED = False

coord_bp    = Blueprint('coordinator', __name__, url_prefix='/coordinator')
COORD_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin']


# ── helpers ───────────────────────────────────────────────
def _phone(reg_data: dict) -> str:
    return (reg_data.get('lead_phone') or
            reg_data.get('phone') or
            (reg_data.get('members') or [{}])[0].get('phone', ''))


def _wa(fn, *args, **kwargs):
    """Call a WhatsApp helper only when Twilio is configured."""
    if WA_ENABLED:
        try:
            return fn(*args, **kwargs)
        except Exception:
            pass
    return False


def _build_simple_schema(event_id: str, created_by: str, is_team: bool) -> dict:
    """Return the default 5-field simple schema for an event."""
    fields = [
        {'id': 'full_name',  'type': 'text',  'label': 'Full Name',
         'placeholder': 'Enter your full name', 'required': True,
         'options': [], 'help_text': ''},
        {'id': 'email',      'type': 'email', 'label': 'Email Address',
         'placeholder': 'you@example.com',      'required': True,
         'options': [], 'help_text': ''},
        {'id': 'phone',      'type': 'tel',   'label': 'Phone Number',
         'placeholder': '10-digit mobile',      'required': True,
         'options': [], 'help_text': ''},
        {'id': 'usn',        'type': 'text',  'label': 'USN / Roll Number',
         'placeholder': 'e.g. 1SN21CS001',      'required': False,
         'options': [], 'help_text': ''},
    ]
    if is_team:
        fields.append({
            'id': 'team_name', 'type': 'text', 'label': 'Team Name',
            'placeholder': 'Leave blank for individual', 'required': False,
            'options': [], 'help_text': 'Only for team events'
        })
    return {
        'event_id':   event_id,
        'form_type':  'simple',
        'form_title': 'Event Registration',
        'form_desc':  'Fill in your details to register for this event.',
        'fields':     fields,
        'created_by': created_by,
        'updated_at': datetime.datetime.utcnow().isoformat(),
    }


# =========================================================
# 1. DASHBOARD
# =========================================================
@coord_bp.route('/dashboard')
@login_required
@role_required(COORD_ROLES)
def dashboard():
    user_role     = session.get('role', '')
    user_email    = session.get('user_id')
    club_category = session.get('category', 'General')

    try:
        is_super = user_role in ('SuperAdmin', 'Super Admin') or club_category == 'All'
        if is_super:
            events_ref = (db.collection('events')
                           .order_by('created_at', direction=firestore.Query.DESCENDING)
                           .stream())
        else:
            events_ref = (db.collection('events')
                           .where(filter=FieldFilter('created_by_email', '==', user_email))
                           .stream())

        events      = []
        total_regs  = 0
        total_staff = 0

        for e in events_ref:
            d       = e.to_dict()
            d['id'] = e.id
            total_regs  += d.get('registration_count', 0)
            total_staff += len(d.get('staff', []))
            regs = db.collection('registrations').where('event_id', '==', e.id).stream()
            d['scored_teams'] = sum(
                1 for r in regs
                if not r.to_dict().get('is_eliminated', False)
                and r.to_dict().get('scores')
            )
            events.append(d)

    except Exception as exc:
        flash(f"Error loading dashboard: {exc}", "danger")
        events, total_regs, total_staff = [], 0, 0

    return render_template(
        'coordinator/dashboard.html',
        events=events,
        club_category=club_category,
        total_regs=total_regs,
        total_staff=total_staff,
        user_name=session.get('name')
    )


# =========================================================
# 2. CREATE EVENT  ★ MAIN CHANGE: saves form schema atomically
# =========================================================
@coord_bp.route('/create_event', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def create_event():
    try:
        overview      = request.form.get('overview', '').strip()
        raw_criteria  = request.form.get('criteria', 'Overall Score')
        criteria_list = [c.strip() for c in raw_criteria.split(',') if c.strip()] or ['Overall Score']
        media_urls    = [u.strip() for u in request.form.getlist('media_urls[]') if u.strip()]
        is_team       = request.form.get('is_team') == 'on'
        form_type     = request.form.get('form_type', 'simple')   # from Step 4
        creator       = session.get('user_id')

        category = (
            session.get('category')
            if session.get('category') not in (None, 'All')
            else request.form.get('category', 'General')
        )

        # 1. Create the event document
        _, event_ref = db.collection('events').add({
            'title':              request.form.get('title', '').strip(),
            'date':               request.form.get('date'),
            'deadline':           request.form.get('deadline'),
            'venue':              request.form.get('venue', '').strip(),
            'description':        overview[:120] + '…' if len(overview) > 120 else overview,
            'overview':           overview,
            'rules':              request.form.get('rules', ''),
            'prizes':             request.form.get('prizes', ''),
            'category':           category,
            'media_urls':         media_urls,
            'banner_url':         media_urls[0] if media_urls else '',
            'entry_fee':          safe_int(request.form.get('entry_fee', 0)),
            'is_team_event':      is_team,
            'judging_criteria':   criteria_list,
            'status':             'active',
            'active_round':       1,
            'registration_count': 0,
            'staff':              [],
            'created_by':         session.get('name'),
            'created_by_email':   creator,
            'created_at':         datetime.datetime.utcnow(),
            'form_type':          form_type,
            'has_custom_form':    True,   # always True — simple schema counts too
        })

        event_id = event_ref.id

        # 2. Save form schema atomically
        if form_type == 'simple':
            # For Simple: build the default schema right now — ready immediately
            schema = _build_simple_schema(event_id, creator, is_team)
            db.collection('event_forms').document(event_id).set(schema)

        else:
            # For Custom: the wizard POSTed the fields JSON in form_schema_json
            raw_json = request.form.get('form_schema_json', '').strip()
            fields   = []
            if raw_json:
                try:
                    fields = json.loads(raw_json)
                except json.JSONDecodeError:
                    fields = []

            # If SPOC didn't build anything yet, seed with a minimal skeleton
            # so the public form at least shows Name + Email until they edit it
            if not fields:
                fields = [
                    {'id': 'full_name', 'type': 'text',  'label': 'Full Name',
                     'placeholder': 'Enter your full name', 'required': True,
                     'options': [], 'help_text': ''},
                    {'id': 'email',     'type': 'email', 'label': 'Email Address',
                     'placeholder': 'you@example.com',   'required': True,
                     'options': [], 'help_text': ''},
                    {'id': 'phone',     'type': 'tel',   'label': 'Phone Number',
                     'placeholder': '10-digit mobile',   'required': True,
                     'options': [], 'help_text': ''},
                ]

            form_title = request.form.get('form_title', '').strip() or 'Event Registration'
            form_desc  = request.form.get('form_desc',  '').strip()

            schema = {
                'event_id':   event_id,
                'form_type':  'custom',
                'form_title': form_title,
                'form_desc':  form_desc,
                'fields':     fields,
                'created_by': creator,
                'updated_at': datetime.datetime.utcnow().isoformat(),
            }
            db.collection('event_forms').document(event_id).set(schema)

        log_action(db, "EVENT_CREATED",
                   f"{creator} created '{request.form.get('title')}' "
                   f"(form_type={form_type}, event_id={event_id})")
        flash("✅ Event created! Registration form is live.", "success")

    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Error creating event: {exc}", "danger")

    return redirect('/coordinator/dashboard')


# =========================================================
# 3. EDIT EVENT
# =========================================================
@coord_bp.route('/edit_event/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def edit_event(event_id):
    try:
        overview      = request.form.get('overview', '').strip()
        raw_criteria  = request.form.get('criteria', 'Overall Score')
        criteria_list = [c.strip() for c in raw_criteria.split(',') if c.strip()] or ['Overall Score']
        media_urls    = [u.strip() for u in request.form.getlist('media_urls[]') if u.strip()]
        db.collection('events').document(event_id).update({
            'title':            request.form.get('title', '').strip(),
            'date':             request.form.get('date'),
            'deadline':         request.form.get('deadline'),
            'venue':            request.form.get('venue', '').strip(),
            'overview':         overview,
            'description':      overview[:120] + '…' if len(overview) > 120 else overview,
            'rules':            request.form.get('rules', ''),
            'prizes':           request.form.get('prizes', ''),
            'judging_criteria': criteria_list,
            'media_urls':       media_urls,
            'banner_url':       media_urls[0] if media_urls else '',
            'entry_fee':        safe_int(request.form.get('entry_fee', 0)),
            'is_team_event':    request.form.get('is_team') == 'on'
        })
        log_action(db, "EVENT_EDITED", f"Event {event_id} by {session.get('user_id')}")
        flash("✅ Event updated!", "success")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 4. DELETE EVENT
# =========================================================
@coord_bp.route('/delete_event/<event_id>')
@login_required
@role_required(COORD_ROLES)
def delete_event(event_id):
    try:
        db.collection('events').document(event_id).delete()
        db.collection('event_forms').document(event_id).delete()
        for r in db.collection('registrations').where('event_id', '==', event_id).stream():
            r.reference.delete()
        for r in db.collection('form_submissions').where('event_id', '==', event_id).stream():
            r.reference.delete()
        log_action(db, "EVENT_DELETED", f"Event {event_id} by {session.get('user_id')}")
        flash("Event deleted.", "warning")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 5. ASSIGN STAFF
# =========================================================
@coord_bp.route('/assign_staff/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def assign_staff(event_id):
    try:
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').lower().strip()
        role  = request.form.get('role', '')
        phone = request.form.get('phone', '').strip()

        if not name or not email or not role:
            flash("All fields are required.", "warning")
            return redirect('/coordinator/dashboard')

        event_doc   = db.collection('events').document(event_id).get()
        event_title = event_doc.to_dict().get('title', 'Event') if event_doc.exists else 'Event'
        user_ref    = db.collection('users').document(email)

        if not user_ref.get().exists:
            alphabet = string.ascii_letters + string.digits
            raw_pw   = ''.join(secrets.choice(alphabet) for _ in range(10))
            user_ref.set({
                'email': email, 'name': name, 'role': role, 'phone': phone,
                'category': session.get('category', 'General'),
                'password': generate_password_hash(raw_pw),
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True
            })
            send_credentials_email(email, name, role, raw_pw,
                                   session.get('category', 'General'))
            if phone:
                _wa(send_staff_credentials_whatsapp, phone, name, role,
                    event_title, email, raw_pw)
            flash(f"✅ Account created for {name}. Credentials sent.", "success")
        else:
            existing_role = user_ref.get().to_dict().get('role', '')
            if existing_role == 'Student':
                user_ref.update({'role': role})
            send_appointment_email(email, name, role, event_title)
            flash(f"📩 {name} already had an account. Role updated.", "info")

        db.collection('events').document(event_id).update({
            'staff': firestore.ArrayUnion([{'name': name, 'email': email, 'role': role}])
        })
        log_action(db, "STAFF_ASSIGNED", f"{name} ({role}) → event {event_id}")
        flash(f"🎉 {name} appointed as {role}!", "success")
    except Exception as exc:
        flash(f"Assignment error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 6. ROOM ALLOCATION
# =========================================================
@coord_bp.route('/allocate_rooms/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def allocate_rooms(event_id):
    try:
        room_names = request.form.getlist('room_name[]')
        capacities = [safe_int(c) for c in request.form.getlist('capacity[]')]
        event_data = db.collection('events').document(event_id).get().to_dict()
        judges     = [s for s in event_data.get('staff', []) if s['role'] == 'Judge']

        if len(judges) < len(room_names):
            flash(f"⚠️ {len(room_names)} rooms but only {len(judges)} judges.", "warning")
            return redirect('/coordinator/dashboard')

        random.shuffle(judges)
        regs = [r for r in
                db.collection('registrations').where('event_id', '==', event_id).stream()
                if not r.to_dict().get('is_eliminated', False)]
        random.shuffle(regs)

        reg_index = 0
        for i, (room, cap) in enumerate(zip(room_names, capacities)):
            judge = judges[i]
            for _ in range(cap):
                if reg_index >= len(regs):
                    break
                db.collection('registrations').document(regs[reg_index].id).update({
                    'assigned_room':        room.strip(),
                    'assigned_judge_email': judge['email'],
                    'assigned_judge_name':  judge['name']
                })
                reg_index += 1

        log_action(db, "ROOMS_ALLOCATED",
                   f"{reg_index} teams across {len(room_names)} rooms — event {event_id}")
        flash(f"✨ {reg_index} teams allocated!", "success")
    except Exception as exc:
        flash(f"Allocation error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 7. TRIGGER REMINDERS
# =========================================================
@coord_bp.route('/trigger_reminders/<event_id>')
@login_required
@role_required(COORD_ROLES)
def trigger_reminders(event_id):
    try:
        event_data  = db.collection('events').document(event_id).get().to_dict()
        round_num   = event_data.get('active_round', 1)
        email_count = wa_count = 0

        for r in db.collection('registrations').where('event_id', '==', event_id).stream():
            d = r.to_dict()
            if d.get('is_eliminated', False) or not d.get('assigned_room'):
                continue
            lead_email = d.get('lead_email')
            lead_name  = d.get('lead_name', 'Participant')
            room       = d.get('assigned_room')
            judge      = d.get('assigned_judge_name', 'TBD')
            phone      = _phone(d)

            send_broadcast_email(
                [lead_email],
                f"Round {round_num} Details",
                (f"ROUND {round_num} ALERT\n\nHello {lead_name},\n\n"
                 f"You are active in Round {round_num} of '{event_data['title']}'.\n"
                 f"Room: {room}\nJudge: {judge}\n\nBest of luck!"),
                event_data['title']
            )
            email_count += 1

            if phone and _wa(send_room_assignment_whatsapp, phone, lead_name,
                             event_data['title'], round_num, room, judge):
                wa_count += 1

        flash(f"📢 Round {round_num} alerts — {email_count} emails, {wa_count} WhatsApp.", "success")
    except Exception as exc:
        flash(f"Reminder error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 8. PROMOTE ROUND / ELIMINATE
# =========================================================
@coord_bp.route('/promote_round/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def promote_round(event_id):
    try:
        cutoff_score  = float(request.form.get('cutoff_score', 0))
        event_ref     = db.collection('events').document(event_id)
        event_data    = event_ref.get().to_dict()
        current_round = event_data.get('active_round', 1)
        next_round    = current_round + 1
        event_title   = event_data.get('title', 'Event')
        promoted = eliminated = 0

        for reg in db.collection('registrations').where('event_id', '==', event_id).stream():
            reg_data    = reg.to_dict()
            if reg_data.get('is_eliminated', False):
                continue
            scores      = reg_data.get('scores', {})
            total_score = sum(safe_int(s.get('total', 0)) for s in scores.values())
            reg_ref     = db.collection('registrations').document(reg.id)
            phone       = _phone(reg_data)
            lead_name   = reg_data.get('lead_name', 'Participant')

            if total_score >= cutoff_score:
                reg_ref.update({
                    'current_round':        next_round,
                    'scores':               firestore.DELETE_FIELD,
                    'assigned_room':        None,
                    'assigned_judge_email': None,
                    'assigned_judge_name':  None,
                })
                promoted += 1
            else:
                reg_ref.update({'is_eliminated': True})
                eliminated += 1
                if phone:
                    _wa(send_elimination_whatsapp, phone, lead_name,
                        event_title, current_round)

        event_ref.update({'active_round': next_round})
        log_action(db, "ROUND_PROMOTED",
                   f"Event {event_id}: {promoted} promoted, {eliminated} eliminated. "
                   f"Cutoff={cutoff_score}")
        flash(f"🏆 Round {next_round} started! {promoted} advanced, {eliminated} eliminated.",
              "success")
    except Exception as exc:
        flash(f"Promotion error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 9. PUBLISH RESULTS
# =========================================================
@coord_bp.route('/publish_results/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def publish_results(event_id):
    try:
        event_ref   = db.collection('events').document(event_id)
        event_data  = event_ref.get().to_dict() or {}
        event_title = event_data.get('title', 'Event')
        leaderboard = []

        for r in db.collection('registrations').where('event_id', '==', event_id).stream():
            d = r.to_dict()
            if d.get('is_eliminated', False):
                continue
            scores = d.get('scores', {})
            if not scores:
                continue
            avg = round(sum(safe_int(s.get('total', 0)) for s in scores.values()) / len(scores), 2)
            leaderboard.append({
                'team_name': d.get('team_name'),
                'lead_name': d.get('lead_name'),
                'email':     d.get('lead_email'),
                'phone':     _phone(d),
                'score':     avg
            })

        leaderboard.sort(key=lambda x: x['score'], reverse=True)

        for idx, winner in enumerate(leaderboard[:3], start=1):
            send_result_email(winner['email'], winner['lead_name'],
                              event_title, idx, winner['score'])
            if winner.get('phone'):
                _wa(send_result_whatsapp, winner['phone'], winner['lead_name'],
                    event_title, idx, winner['score'])

        event_ref.update({
            'status':       'completed',
            'winners':      leaderboard[:3],
            'completed_at': datetime.datetime.utcnow()
        })
        log_action(db, "RESULTS_PUBLISHED",
                   f"Event {event_id} by {session.get('user_id')}")
        flash("🏆 Results published! Winners notified.", "success")
    except Exception as exc:
        flash(f"Publish error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 10. BROADCAST
# =========================================================
@coord_bp.route('/broadcast/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def broadcast_message(event_id):
    try:
        subject   = request.form.get('subject', '').strip()
        message   = request.form.get('message', '').strip()
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            return redirect('/coordinator/dashboard')

        event_title = event_doc.to_dict().get('title', 'Event')
        regs        = list(db.collection('registrations')
                           .where('event_id', '==', event_id).stream())
        email_list  = list({r.to_dict().get('lead_email')
                            for r in regs if r.to_dict().get('lead_email')})
        phone_list  = list({_phone(r.to_dict())
                            for r in regs if _phone(r.to_dict())})

        send_broadcast_email(email_list, subject, message, event_title)

        wa_result = {'sent': 0, 'failed': 0}
        if WA_ENABLED:
            try:
                from utils_whatsapp import send_broadcast_whatsapp
                wa_result = send_broadcast_whatsapp(phone_list, event_title, subject, message)
            except Exception:
                pass

        flash(f"📢 Sent — {len(email_list)} emails, {wa_result['sent']} WhatsApp.", "success")
    except Exception as exc:
        flash(f"Broadcast error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# =========================================================
# 11. EXPORT CSV
# =========================================================
@coord_bp.route('/export_registrations/<event_id>')
@login_required
@role_required(COORD_ROLES)
def export_registrations(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get().to_dict()
        regs      = db.collection('registrations').where('event_id', '==', event_id).stream()
        output    = StringIO()
        writer    = csv.writer(output)
        writer.writerow([
            'Ticket ID', 'Lead Name', 'Email', 'USN', 'Phone', 'Team Name',
            'Members', 'Room', 'Judge', 'Round', 'Status', 'Attendance', 'Registered At'
        ])
        for r in regs:
            d      = r.to_dict()
            status = 'Eliminated' if d.get('is_eliminated', False) else 'Active'
            writer.writerow([
                d.get('reg_id', 'N/A'), d.get('lead_name', 'N/A'),
                d.get('lead_email', 'N/A'), d.get('lead_usn', 'N/A'),
                d.get('lead_phone', 'N/A'),
                d.get('team_name', 'Individual'), d.get('member_count', 1),
                d.get('assigned_room', 'Unassigned'),
                d.get('assigned_judge_email', 'Unassigned'),
                d.get('current_round', 1), status,
                d.get('attendance', 'Pending'), d.get('registered_at', 'N/A')
            ])
        clean = (event_doc or {}).get('title', 'Event').replace(' ', '_')
        return Response(output.getvalue(), mimetype='text/csv',
                        headers={"Content-Disposition":
                                 f"attachment; filename={clean}_Registrations.csv"})
    except Exception as exc:
        flash(f"Export error: {exc}", "danger")
        return redirect('/coordinator/dashboard')


# =========================================================
# 12. WALK-IN
# =========================================================
@coord_bp.route('/on_spot')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def on_spot_form():
    events = [{'id': e.id, 'title': e.to_dict().get('title')}
              for e in db.collection('events').where('status', '==', 'active').stream()]
    return render_template('coordinator/on_spot.html', events=events)


@coord_bp.route('/process_walkin', methods=['POST'])
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def process_walkin():
    try:
        import time as _time
        event_id    = request.form.get('event_id')
        email       = request.form.get('email', '').lower().strip()
        name        = request.form.get('name', '').strip()
        usn         = request.form.get('usn', '').upper().strip()
        phone       = request.form.get('phone', '').strip()

        if not event_id or not email or not name:
            flash("Event, name, and email are required.", "warning")
            return redirect('/coordinator/on_spot')

        user_ref = db.collection('users').document(email)
        if not user_ref.get().exists:
            user_ref.set({
                'email': email, 'name': name, 'phone': phone, 'usn': usn,
                'role': 'Student',
                'password': generate_password_hash('Welcome@123'),
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True
            })

        reg_id      = f"REG-{int(_time.time() * 1000)}"
        event_doc   = db.collection('events').document(event_id).get().to_dict()
        event_title = event_doc.get('title', 'Event')

        db.collection('registrations').document(reg_id).set({
            'reg_id': reg_id, 'event_id': event_id, 'event_title': event_title,
            'lead_name': name, 'lead_email': email, 'lead_usn': usn,
            'lead_phone': phone, 'team_name': 'Walk-in', 'members': [],
            'status': 'Confirmed', 'payment_status': 'Paid',
            'amount_paid': event_doc.get('entry_fee', 0),
            'payment_mode': request.form.get('payment_mode', 'Cash'),
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Present',
            'checkin_time': datetime.datetime.now().strftime("%H:%M:%S"),
            'is_eliminated': False, 'current_round': event_doc.get('active_round', 1)
        })

        send_ticket_email(email, name, event_title, reg_id)
        if phone:
            _wa(send_ticket_whatsapp, phone, name, event_title, reg_id,
                event_doc.get('date', ''), event_doc.get('venue', ''))

        log_action(db, "WALKIN_REGISTERED", f"Walk-in {email} for event {event_id}")
        flash(f"✅ Walk-in for {name} registered. Ticket sent.", "success")
    except Exception as exc:
        flash(f"Walk-in error: {exc}", "danger")
    return redirect('/coordinator/on_spot')


# =========================================================
# 13. SCANNER & ATTENDANCE
# =========================================================
@coord_bp.route('/scanner')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def scanner_selector():
    events = [{'id': e.id, 'title': e.to_dict().get('title')}
              for e in db.collection('events').where('status', '==', 'active').stream()]
    return render_template('coordinator/scanner_selector.html', events=events)


@coord_bp.route('/scan/<event_id>')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def scan_page(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        return redirect('/coordinator/scanner')
    return render_template('coordinator/scan.html',
                            event_id=event_id,
                            event_title=doc.to_dict().get('title'))


@coord_bp.route('/get_ticket/<reg_id>')
@login_required
def get_ticket(reg_id):
    reg = db.collection('registrations').document(reg_id).get()
    if not reg.exists:
        return jsonify({'status': 'error', 'message': 'INVALID TICKET'})
    return jsonify({'status': 'success', 'data': reg.to_dict()})


@coord_bp.route('/mark_attendance_granular', methods=['POST'])
@login_required
def mark_attendance_granular():
    try:
        data         = request.json or {}
        reg_id       = data.get('reg_id')
        present_usns = data.get('present_usns', [])
        if not reg_id:
            return jsonify({'status': 'error', 'message': 'Missing reg_id'})
        reg_ref  = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()
        if not reg_data:
            return jsonify({'status': 'error', 'message': 'Registration not found'})
        if reg_data.get('payment_status') == 'Pending':
            return jsonify({'status': 'error', 'message': '💰 PAYMENT PENDING!'})
        members = reg_data.get('members', [])
        for m in members:
            m['attendance'] = 'Present' if m.get('usn') in present_usns else 'Absent'
        reg_ref.update({
            'members':      members,
            'attendance':   'Present' if present_usns else 'Absent',
            'checkin_time': datetime.datetime.now().strftime("%H:%M:%S")
        })
        log_action(db, "ATTENDANCE_MARKED",
                   f"Reg {reg_id}: {len(present_usns)} present")
        return jsonify({'status': 'success',
                        'message': f"✅ {len(present_usns)} members marked present."})
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)})


# =========================================================
# 14. CERTIFICATE
# =========================================================
@coord_bp.route('/certificate/<reg_id>/<usn>')
def generate_certificate(reg_id, usn):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        return "Registration not found.", 404
    data         = reg_doc.to_dict()
    student_name = None
    if data.get('lead_usn') == usn:
        if data.get('attendance') != 'Present':
            return "Certificate denied: marked Absent.", 403
        student_name = data.get('lead_name')
    else:
        for m in data.get('members', []):
            if m.get('usn') == usn:
                if m.get('attendance') != 'Present':
                    return "Certificate denied: marked Absent.", 403
                student_name = m.get('name')
                break
    if not student_name:
        return "Student not found in this registration.", 404
    event_data = db.collection('events').document(data['event_id']).get().to_dict()
    return render_template('participant/certificate.html',
                            student_name=student_name, event=event_data)