"""
routes_forms.py  —  Form Builder + Public Registration

Flow:
  SPOC creates event via wizard → form schema saved atomically to event_forms/<id>
  Participant clicks Register on homepage → /forms/register/<id> renders that schema
  Participant submits → /forms/submit/<id> validates, saves registration, sends notifications

URL map:
  GET  /forms/builder/<event_id>          — edit form after creation
  POST /forms/save/<event_id>             — AJAX save from builder
  GET  /forms/register/<event_id>         — PUBLIC registration page
  POST /forms/submit/<event_id>           — PUBLIC form submission
  GET  /forms/responses/<event_id>        — coordinator sees all submissions
  GET  /forms/responses/export/<event_id> — CSV export
  GET  /forms/schema/<event_id>           — JSON API (used by builder)
"""
import csv
import datetime
import io
import json
import re
import secrets
import string
import time

from flask import (Blueprint, Response, current_app, flash, jsonify,
                   redirect, render_template, request, session)
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import generate_password_hash

from models import db
from utils import login_required, role_required, log_action, safe_int
from utils_email import send_registration_confirmed_email

from extensions import limiter

# WhatsApp optional
try:
    from utils_whatsapp import send_ticket_whatsapp
    WA_ENABLED = True
except ImportError:
    WA_ENABLED = False

from typing import Optional

forms_bp      = Blueprint('forms', __name__, url_prefix='/forms')
BUILDER_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin']


# =========================================================
# HELPERS
# =========================================================

def _get_form(event_id: str) -> Optional[dict]:
    doc = db.collection('event_forms').document(event_id).get()
    return doc.to_dict() if doc.exists else None


def _validate_submission(schema: dict, form_data: dict) -> list:
    errors = []
    for field in schema.get('fields', []):
        fid      = field.get('id', '')
        label    = field.get('label', fid)
        required = field.get('required', False)
        ftype    = field.get('type', 'text')

        if ftype in ('heading', 'paragraph', 'divider'):
            continue

        raw = form_data.get(fid)
        if isinstance(raw, list):
            value = raw
        else:
            value = str(raw or '').strip()

        if required:
            if not value or value == []:
                errors.append(f"'{label}' is required.")
                continue

        if ftype == 'email' and value:
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', str(value)):
                errors.append(f"'{label}' must be a valid email address.")

        if ftype == 'tel' and value:
            digits = re.sub(r'\D', '', str(value))
            if len(digits) < 10:
                errors.append(f"'{label}' must be a valid phone number (min 10 digits).")

        if ftype == 'number' and value:
            try:
                n = float(str(value))
                if field.get('min') != '' and field.get('min') is not None:
                    if n < float(field['min']):
                        errors.append(f"'{label}' must be at least {field['min']}.")
                if field.get('max') != '' and field.get('max') is not None:
                    if n > float(field['max']):
                        errors.append(f"'{label}' must be at most {field['max']}.")
            except (ValueError, TypeError):
                errors.append(f"'{label}' must be a number.")

    return errors


def _extract_core(answers: dict) -> dict:
    """
    Pull the standard identity fields out of any form's answers dict.
    Handles both standard field IDs and common synonyms.
    """
    def first(*keys):
        for k in keys:
            v = str(answers.get(k) or '').strip()
            if v:
                return v
        return ''

    return {
        'email':     first('email', 'email_address'),
        'full_name': first('full_name', 'name', 'participant_name'),
        'phone':     first('phone', 'phone_number', 'mobile', 'contact'),
        'usn':       first('usn', 'roll_number', 'roll_no', 'id_number'),
        'team_name': first('team_name', 'team', 'group_name') or 'Individual',
    }


def _simple_schema_fallback(is_team: bool = False) -> dict:
    """Used only when event_forms doc is truly missing (should not happen post-wizard)."""
    fields = [
        {'id': 'full_name', 'type': 'text',  'label': 'Full Name',
         'placeholder': 'Enter your full name', 'required': True,
         'options': [], 'help_text': ''},
        {'id': 'email',     'type': 'email', 'label': 'Email Address',
         'placeholder': 'you@example.com',    'required': True,
         'options': [], 'help_text': ''},
        {'id': 'phone',     'type': 'tel',   'label': 'Phone Number',
         'placeholder': '10-digit mobile',   'required': True,
         'options': [], 'help_text': ''},
        {'id': 'usn',       'type': 'text',  'label': 'USN / Roll Number',
         'placeholder': 'e.g. 1SN21CS001',   'required': False,
         'options': [], 'help_text': ''},
    ]
    if is_team:
        fields.append({'id': 'team_name', 'type': 'text',
                        'label': 'Team Name', 'placeholder': 'Leave blank if solo',
                        'required': False, 'options': [], 'help_text': ''})
    return {
        'form_type': 'simple', 'form_title': 'Event Registration',
        'form_desc': 'Fill in your details to register.', 'fields': fields
    }


# =========================================================
# 1. FORM BUILDER PAGE  (edit after creation)
# =========================================================
@forms_bp.route('/builder/<event_id>')
@login_required
@role_required(BUILDER_ROLES)
def builder(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/coordinator/dashboard')

    event       = event_doc.to_dict()
    event['id'] = event_id
    existing    = _get_form(event_id)

    return render_template(
        'coordinator/form_builder.html',
        event=event,
        existing_form=existing,
        form_json=json.dumps(existing) if existing else 'null'
    )


# =========================================================
# 2. SAVE FORM (AJAX — from builder or wizard)
# =========================================================
@forms_bp.route('/save/<event_id>', methods=['POST'])
@login_required
@role_required(BUILDER_ROLES)
def save_form(event_id):
    try:
        payload    = request.get_json(force=True) or {}
        form_type  = payload.get('form_type', 'simple')
        fields_raw = payload.get('fields', [])
        form_title = payload.get('form_title', 'Registration Form').strip()
        form_desc  = payload.get('form_desc', '').strip()

        clean_fields = []
        for i, f in enumerate(fields_raw):
            clean_fields.append({
                'id':          f.get('id') or f"field_{i}",
                'type':        f.get('type', 'text'),
                'label':       f.get('label', f'Field {i+1}'),
                'placeholder': f.get('placeholder', ''),
                'required':    bool(f.get('required', False)),
                'options':     f.get('options', []),
                'min':         f.get('min', ''),
                'max':         f.get('max', ''),
                'help_text':   f.get('help_text', ''),
            })

        schema = {
            'event_id':   event_id,
            'form_type':  form_type,
            'form_title': form_title,
            'form_desc':  form_desc,
            'fields':     clean_fields,
            'created_by': session.get('user_id'),
            'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        db.collection('event_forms').document(event_id).set(schema)
        db.collection('events').document(event_id).update({
            'has_custom_form': True,
            'form_type':       form_type
        })

        log_action(db, "FORM_SAVED",
                   f"Event {event_id}: {form_type} form saved by {session.get('user_id')}")
        return jsonify({'status': 'ok', 'message': 'Form saved!'})

    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


# =========================================================
# 3. PUBLIC REGISTRATION PAGE
# =========================================================
@forms_bp.route('/register/<event_id>')
@limiter.limit("60 per hour")
def registration_page(event_id):
    # Fetch event
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return render_template('404.html'), 404

    event       = event_doc.to_dict()
    event['id'] = event_id

    # Deadline check
    deadline = event.get('deadline') or event.get('reg_deadline', '')
    today    = datetime.datetime.now().strftime('%Y-%m-%d')
    if deadline and today > deadline:
        return render_template('public/registration_closed.html', event=event)

    # Capacity check
    max_cap = safe_int((event.get('limits') or {}).get('max_participants', 0))
    is_waitlist = False
    if max_cap and event.get('registration_count', 0) >= max_cap:
        is_waitlist = True

    # Already registered?
    is_registered = False
    if session.get('user_id'):
        q = (db.collection('registrations')
               .where(filter=FieldFilter('event_id',   '==', event_id))
               .where(filter=FieldFilter('lead_email', '==', session['user_id']))
               .limit(1).stream())
        is_registered = any(q)

    # Load schema — always exists after wizard, fallback just in case
    schema = _get_form(event_id) or _simple_schema_fallback(
        is_team=event.get('is_team_event', False)
    )

    return render_template(
        'public/registration_form.html',
        event=event,
        schema=schema,
        is_registered=is_registered,
        is_waitlist=is_waitlist
    )


# =========================================================
# 4. SUBMIT FORM
# =========================================================
@forms_bp.route('/submit/<event_id>', methods=['POST'])
@limiter.limit("20 per hour")
def submit_form(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/')
        event_data = event_doc.to_dict()

        schema = _get_form(event_id) or {
            'fields': _simple_schema_fallback(
                event_data.get('is_team_event', False))['fields']
        }

        # Collect all answers — values are str for most fields, list[str] for checkbox_group
        answers: dict = {}
        for field in schema.get('fields', []):
            fid = field.get('id', '')
            if not fid or field.get('type') in ('heading', 'paragraph', 'divider'):
                continue
            if field['type'] == 'checkbox_group':
                answers[fid] = request.form.getlist(fid)
            else:
                answers[fid] = request.form.get(fid, '').strip()

        # Validate
        errors = _validate_submission(schema, answers)
        if errors:
            for err in errors:
                flash(err, 'danger')
            return redirect(f'/forms/register/{event_id}')

        # Extract core fields
        core = _extract_core(answers)
        email     = core['email'].lower()
        full_name = core['full_name']
        phone     = core['phone']
        usn       = core['usn'].upper()
        team_name = core['team_name']

        if not email or not full_name:
            flash("Name and email are required.", "warning")
            return redirect(f'/forms/register/{event_id}')

        # Duplicate check
        existing = list(
            db.collection('registrations')
              .where(filter=FieldFilter('event_id',   '==', event_id))
              .where(filter=FieldFilter('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            flash("🚫 You have already registered for this event.", "warning")
            return redirect('/')

        # Auto-create account
        user_ref     = db.collection('users').document(email)
        is_new_user  = not user_ref.get().exists
        raw_password = ''
        if is_new_user:
            alphabet     = string.ascii_letters + string.digits
            raw_password = ''.join(secrets.choice(alphabet) for _ in range(10))
            user_ref.set({
                'email':               email,
                'name':                full_name,
                'role':                'Student',
                'category':            'General',
                'phone':               phone,
                'password':            generate_password_hash(raw_password),
                'created_at':          datetime.datetime.now().strftime('%Y-%m-%d'),
                'needs_password_reset': True
            })
            # ✅ Do NOT show raw password in flash — it is emailed securely
            flash(
                "🆕 Account created! Check your email for your login credentials.",
                "info"
            )

        # Build members list — lead + any member_N_* fields from team forms
        members = [{'role': 'Lead', 'name': full_name,
                    'email': email, 'usn': usn, 'phone': phone}]
        for i in range(1, 10):
            m_name = str(answers.get(f'member_{i}_name') or '').strip()
            if not m_name:
                break
            members.append({
                'role':  'Member',
                'name':  m_name,
                'email': str(answers.get(f'member_{i}_email') or '').strip().lower(),
                'usn':   str(answers.get(f'member_{i}_usn')   or '').strip().upper(),
                'phone': str(answers.get(f'member_{i}_phone') or '').strip(),
            })

        # Build registration
        reg_id   = f"REG-{int(time.time() * 1000)}"
        reg_data = {
            'reg_id':          reg_id,
            'event_id':        event_id,
            'event_title':     event_data.get('title'),
            'lead_email':      email,
            'lead_name':       full_name,
            'lead_usn':        usn,
            'lead_phone':      phone,
            'team_name':       team_name,
            'members':         members,
            'member_count':    len(members),
            'attendance':      'Pending',
            'registered_at':   datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_eliminated':   False,
            'current_round':   1,
            'form_answers':    answers,
            'form_type':       schema.get('form_type', 'simple'),
        }

        # Capacity check — if event is at capacity, add to waitlists instead
        max_cap = safe_int((event_data.get('limits') or {}).get('max_participants', 0))
        current_count = safe_int(event_data.get('registration_count', 0))
        if max_cap and current_count >= max_cap:
            # Check if already on waitlists
            wl_existing = list(
                db.collection('waitlists')
                  .where(filter=FieldFilter('event_id', '==', event_id))
                  .where(filter=FieldFilter('email', '==', email))
                  .where(filter=FieldFilter('status', '==', 'waiting'))
                  .limit(1).stream()
            )
            if wl_existing:
                flash("You are already on the waitlist for this event.", "info")
                return redirect('/participant/dashboard')

            # Count existing waitlist to get position
            wl_count = 0
            for _ in (
                db.collection('waitlists')
                  .where(filter=FieldFilter('event_id', '==', event_id))
                  .where(filter=FieldFilter('status', '==', 'waiting'))
                  .stream()
            ):
                wl_count += 1

            wl_id = f"WL-{int(time.time() * 1000)}"
            wl_entry = {
                'id':            wl_id,
                'event_id':      event_id,
                'event_title':   event_data.get('title', ''),
                'email':         email,
                'user_email':    email,
                'name':          full_name,
                'phone':         phone,
                'payment_status': 'Free' if not fee else 'Pending',
                'amount_paid':   0,
                'joined_at':     datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'status':        'waiting',
                'position':      wl_count + 1,
                'reg_data':      reg_data,
            }
            db.collection('waitlists').document(wl_id).set(wl_entry)

            # Auto-login the student
            session['user_id']  = email
            session['name']     = full_name
            session['role']     = 'Student'
            session['category'] = 'General'

            flash(f"This event is full! You've joined the waitlist at position #{wl_count + 1}. We'll email you if a spot opens.", "info")
            return redirect('/participant/dashboard')

        # Save submission analytics separately
        db.collection('form_submissions').add({
            'event_id':     event_id,
            'reg_id':       reg_id,
            'email':        email,
            'name':         full_name,
            'answers':      answers,
            'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

        # Free vs paid
        fee = safe_int(event_data.get('entry_fee', 0))
        if fee > 0:
            reg_data.update({
                'status':         'Pending Payment',
                'payment_status': 'Pending',
                'amount_paid':    0
            })
            session['pending_reg_data'] = reg_data
            return redirect(f'/payment/checkout/{event_id}')

        reg_data.update({
            'status':         'Confirmed',
            'payment_status': 'Free',
            'amount_paid':    0
        })
        db.collection('registrations').document(reg_id).set(reg_data)
        # Atomic increment — safe under concurrent registrations
        db.collection('events').document(event_id).update({
            'registration_count': firestore.Increment(1)
        })

        # Notifications — confirmation only; QR ticket sent 1 day before event
        send_registration_confirmed_email(
            email, full_name, event_data.get('title', ''),
            event_date=event_data.get('date', ''),
            venue=event_data.get('venue', ''),
            is_new_user=is_new_user,
            raw_password=raw_password,
        )
        if phone and WA_ENABLED:
            try:
                send_ticket_whatsapp(
                    phone=phone, name=full_name,
                    event_title=event_data.get('title', ''),
                    reg_id=reg_id,
                    event_date=event_data.get('date', ''),
                    venue=event_data.get('venue', '')
                )
            except Exception:
                pass

        log_action(db, "FORM_SUBMISSION",
                   f"{email} registered for event {event_id} via form")

        # Auto-login before redirecting
        session['user_id']  = email
        session['name']     = full_name
        session['role']     = 'Student'
        session['category'] = 'General'

        # Redirect to confirmation page — not the ticket (QR gated until day before)
        session['reg_confirmed'] = {
            'reg_id':      reg_id,
            'event_title': event_data.get('title', ''),
            'event_date':  event_data.get('date', ''),
            'venue':       event_data.get('venue', ''),
            'is_new_user': is_new_user,
            'raw_password': raw_password if is_new_user else '',
        }
        return redirect('/registration/confirmed')

    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Submission failed: {exc}", "danger")
        return redirect(f'/forms/register/{event_id}')


# =========================================================
# 5. VIEW RESPONSES
# =========================================================
@forms_bp.route('/responses/<event_id>')
@login_required
@role_required(BUILDER_ROLES)
def view_responses(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/coordinator/dashboard')

    event       = event_doc.to_dict()
    event['id'] = event_id
    schema      = _get_form(event_id) or {'fields': []}

    submissions = []
    for doc in (db.collection('form_submissions')
                  .where(filter=FieldFilter('event_id', '==', event_id)).stream()):
        d           = doc.to_dict()
        d['doc_id'] = doc.id
        submissions.append(d)

    submissions.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)

    return render_template(
        'coordinator/form_responses.html',
        event=event, schema=schema, submissions=submissions
    )


# =========================================================
# 6. EXPORT CSV
# =========================================================
@forms_bp.route('/responses/export/<event_id>')
@login_required
@role_required(BUILDER_ROLES)
def export_responses(event_id):
    event_doc = db.collection('events').document(event_id).get()
    event     = event_doc.to_dict() if event_doc.exists else {}
    schema    = _get_form(event_id) or {'fields': []}
    fields    = schema.get('fields', [])

    submissions = [doc.to_dict() for doc in
                   db.collection('form_submissions')
                     .where(filter=FieldFilter('event_id', '==', event_id)).stream()]

    output = io.StringIO()
    writer = csv.writer(output)

    header = ['Submitted At', 'Name', 'Email']
    header += [f.get('label', f['id']) for f in fields
               if f['id'] not in ('full_name', 'name', 'email')
               and f.get('type') not in ('heading', 'paragraph', 'divider')]
    writer.writerow(header)

    for s in submissions:
        answers = s.get('answers', {})
        row     = [s.get('submitted_at', ''), s.get('name', ''), s.get('email', '')]
        for f in fields:
            if (f['id'] in ('full_name', 'name', 'email') or
                    f.get('type') in ('heading', 'paragraph', 'divider')):
                continue
            val = answers.get(f['id'], '')
            row.append(', '.join(val) if isinstance(val, list) else val)
        writer.writerow(row)

    title = event.get('title', 'Event').replace(' ', '_')
    return Response(
        output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={title}_responses.csv'}
    )


# =========================================================
# 7. SCHEMA JSON API  (used by form_builder.html JS)
# =========================================================
@forms_bp.route('/schema/<event_id>')
def get_schema(event_id):
    schema = _get_form(event_id)
    if not schema:
        event_doc = db.collection('events').document(event_id).get()
        is_team   = event_doc.to_dict().get('is_team_event', False) if event_doc.exists else False
        return jsonify(_simple_schema_fallback(is_team))
    return jsonify(schema)


# =========================================================
# 8. AI FORM GENERATION  (Gemini + keyword fallback)
# =========================================================
SUPPORTED_FIELD_TYPES = {
    'text', 'textarea', 'email', 'tel', 'number', 'date', 'url',
    'select', 'radio', 'checkbox_group', 'checkbox',
    'heading', 'paragraph', 'divider'
}


def _slug(label: str, used: set) -> str:
    base = re.sub(r'[^a-z0-9]+', '_', (label or 'field').lower()).strip('_') or 'field'
    fid, n = base, 2
    while fid in used:
        fid = f"{base}_{n}"
        n += 1
    used.add(fid)
    return fid


def _normalize_fields(raw_fields) -> list:
    """Sanitise LLM/keyword output into valid form_builder schema fields."""
    if not isinstance(raw_fields, list):
        return []
    used, clean = set(), []
    for i, f in enumerate(raw_fields):
        if not isinstance(f, dict):
            continue
        ftype = str(f.get('type', 'text')).lower().strip()
        if ftype not in SUPPORTED_FIELD_TYPES:
            ftype = 'text'
        label = str(f.get('label') or f'Field {i+1}').strip()[:120]
        fid   = str(f.get('id') or '').strip() or _slug(label, used)
        if fid in used:
            fid = _slug(label, used)
        else:
            used.add(fid)
        opts = f.get('options') or []
        if not isinstance(opts, list):
            opts = []
        opts = [str(o).strip()[:80] for o in opts if str(o).strip()]
        clean.append({
            'id':          fid,
            'type':        ftype,
            'label':       label,
            'placeholder': str(f.get('placeholder') or '')[:120],
            'required':    bool(f.get('required', False)),
            'options':     opts,
            'min':         f.get('min', ''),
            'max':         f.get('max', ''),
            'help_text':   str(f.get('help_text') or '')[:200],
        })
    return clean


def _keyword_generate(description: str, is_team: bool = False) -> list:
    """Dumb keyword matcher — always works, no API needed."""
    text = (description or '').lower()
    fields, used = [], set()

    def add(label, ftype, **extra):
        fid = _slug(label, used)
        fields.append({
            'id': fid, 'type': ftype, 'label': label,
            'placeholder': extra.get('placeholder', ''),
            'required':    extra.get('required', False),
            'options':     extra.get('options', []),
            'min': extra.get('min', ''), 'max': extra.get('max', ''),
            'help_text': '',
        })

    # Always: name + email
    add('Full Name',     'text',  placeholder='Enter your full name', required=True)
    add('Email Address', 'email', placeholder='you@example.com',      required=True)

    if re.search(r'\b(phone|mobile|whatsapp|contact|number)\b', text):
        add('Phone Number', 'tel', placeholder='10-digit mobile', required=True)

    if re.search(r'\b(usn|srn|roll|registration no|reg no|student id)\b', text):
        add('USN / Roll Number', 'text', placeholder='e.g. 1SN21CS001', required=True)

    if re.search(r'\b(college|institution|university|school)\b', text):
        add('College / Institution', 'text', placeholder='Your college name', required=True)

    if re.search(r'\b(branch|department|stream|course)\b', text):
        add('Branch / Department', 'text', placeholder='e.g. CSE, ECE', required=False)

    if re.search(r'\b(year|semester|sem)\b', text):
        add('Year of Study', 'select',
            options=['1st Year', '2nd Year', '3rd Year', '4th Year'], required=True)

    if re.search(r'\bgender\b', text):
        add('Gender', 'radio', options=['Male', 'Female', 'Prefer not to say'])

    if re.search(r'\b(t[- ]?shirt|tshirt|tee|size)\b', text):
        add('T-Shirt Size', 'select', options=['S', 'M', 'L', 'XL', 'XXL'])

    if re.search(r'\b(diet|food|veg|meal)\b', text):
        add('Dietary Preference', 'radio', options=['Veg', 'Non-Veg', 'Jain', 'Vegan'])

    if re.search(r'\b(github|portfolio|link|url|website)\b', text):
        add('GitHub / Portfolio URL', 'url', placeholder='https://github.com/you')

    if re.search(r'\b(linkedin)\b', text):
        add('LinkedIn Profile', 'url', placeholder='https://linkedin.com/in/you')

    if re.search(r'\b(resume|cv)\b', text):
        add('Resume / CV Link', 'url', placeholder='Google Drive or link')

    if re.search(r'\b(abstract|pitch|idea|proposal|description)\b', text):
        add('Project / Idea Description', 'textarea',
            placeholder='Tell us about your idea (100–300 words)')

    if re.search(r'\b(experience|skill)\b', text):
        add('Relevant Skills / Experience', 'textarea',
            placeholder='Languages, frameworks, past projects')

    if re.search(r'\b(allerg|medical|health)\b', text):
        add('Allergies / Medical Notes', 'textarea', placeholder='Leave blank if none')

    if re.search(r'\b(emergency|guardian|parent)\b', text):
        add('Emergency Contact Number', 'tel', placeholder='10-digit number')

    if re.search(r'\b(dob|date of birth|birthday)\b', text):
        add('Date of Birth', 'date')

    if re.search(r'\b(accommodation|stay|hostel|outstation)\b', text):
        add('Need Accommodation?', 'radio', options=['Yes', 'No'])

    if re.search(r'\b(hear|source|how did you)\b', text):
        add('How did you hear about this event?', 'select',
            options=['Instagram', 'WhatsApp', 'College Notice', 'Friend', 'Other'])

    if is_team or re.search(r'\b(team|group|squad)\b', text):
        add('Team Name', 'text', placeholder='Your team name', required=True)
        add('Team Size', 'number', placeholder='e.g. 4', min=1, max=10)

    # De-dupe by label
    seen, deduped = set(), []
    for f in fields:
        key = f['label'].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    return deduped


def _gemini_generate(description: str, is_team: bool) -> list:
    """Ask Gemini for a structured schema. Returns [] on any failure."""
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        return []
    try:
        from google import genai  # already in requirements
        client = genai.Client(api_key=api_key)
        prompt = (
            "You are a form-schema generator for a college event registration system.\n"
            "Given the SPOC's plain-English description, output ONLY a JSON array of "
            "form fields (no prose, no markdown fences). Each field must match this shape:\n"
            '{"id": "snake_case_id", "type": "<type>", "label": "Human label", '
            '"placeholder": "", "required": true/false, "options": ["..."], '
            '"min": "", "max": "", "help_text": ""}\n\n'
            f"Allowed types: {', '.join(sorted(SUPPORTED_FIELD_TYPES))}.\n"
            "Rules:\n"
            "- Always include Full Name (text, required) and Email (email, required) "
            "as the first two fields.\n"
            "- Use 'select' or 'radio' whenever the description implies a fixed set of "
            "choices (e.g. sizes, year, gender, veg/non-veg).\n"
            "- Use 'tel' for phone/whatsapp, 'url' for links, 'textarea' for long answers, "
            "'number' for counts.\n"
            "- Mark a field required only if clearly essential.\n"
            "- Keep it under 15 fields. Omit 'options' when not applicable.\n"
            f"- Team event: {is_team}. If true, include Team Name.\n\n"
            f"Description:\n{description}\n\n"
            "Output: JSON array only."
        )
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = (resp.text or '').strip()
        # strip markdown fences if the model added them anyway
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.IGNORECASE).strip()
        # trim to the outermost JSON array
        first, last = raw.find('['), raw.rfind(']')
        if first == -1 or last == -1 or last < first:
            return []
        parsed = json.loads(raw[first:last + 1])
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:
        current_app.logger.warning("Gemini form-gen failed: %s", exc)
        return []


@forms_bp.route('/ai_generate', methods=['POST'])
@login_required
@role_required(BUILDER_ROLES)
def ai_generate():
    """
    Request:  { description: str, is_team: bool }
    Response: { source: 'ai' | 'keyword', fields: [...] }
    """
    try:
        payload     = request.get_json(force=True) or {}
        description = str(payload.get('description', '')).strip()
        is_team     = bool(payload.get('is_team', False))

        if not description:
            return jsonify({'status': 'error', 'message': 'Please describe your form.'}), 400

        fields = _normalize_fields(_gemini_generate(description, is_team))
        source = 'ai' if fields else 'keyword'
        if not fields:
            fields = _normalize_fields(_keyword_generate(description, is_team))

        return jsonify({'status': 'ok', 'source': source, 'fields': fields})
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500
