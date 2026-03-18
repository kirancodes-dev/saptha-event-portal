import collections
import datetime
import json

from flask import Blueprint, flash, redirect, render_template, request, session
from google.cloud import firestore
from werkzeug.security import generate_password_hash

from models import db
from utils import login_required, role_required, log_action
from utils_email import send_credentials_email

admin_bp    = Blueprint('admin', __name__, url_prefix='/admin')
SUPER_ROLES = ['SuperAdmin', 'Super Admin']


# =========================================================
# 1. SUPER ADMIN DASHBOARD
# =========================================================
@admin_bp.route('/dashboard')
@login_required
@role_required(SUPER_ROLES)
def dashboard():
    try:
        events_ref = (db.collection('events')
                        .order_by('created_at', direction=firestore.Query.DESCENDING)
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

        users_ref  = db.collection('users').stream()
        user_stats = {'total': 0, 'students': 0, 'staff': 0}
        for u in users_ref:
            role = u.to_dict().get('role', '')
            user_stats['total'] += 1
            if role == 'Student':
                user_stats['students'] += 1
            else:
                user_stats['staff'] += 1

        audit_log = []
        try:
            logs = (db.collection('audit_log')
                      .order_by('timestamp', direction=firestore.Query.DESCENDING)
                      .limit(20).stream())
            audit_log = [l.to_dict() for l in logs]
        except Exception:
            pass

    except Exception as exc:
        flash(f"Dashboard error: {exc}", "danger")
        events, total_regs, total_staff, user_stats, audit_log = [], 0, 0, {}, []

    return render_template(
        'admin/dashboard.html',
        events=events,
        total_regs=total_regs,
        total_staff=total_staff,
        user_stats=user_stats,
        audit_log=audit_log,
        user_name=session.get('name')
    )


# =========================================================
# 2. ANALYTICS DASHBOARD
# =========================================================
@admin_bp.route('/analytics')
@login_required
@role_required(SUPER_ROLES)
def analytics():
    try:
        # Fetch all registrations and events
        all_regs   = [r.to_dict() for r in db.collection('registrations').stream()]
        events_map = {}
        for e in db.collection('events').stream():
            d = e.to_dict(); d['id'] = e.id
            events_map[e.id] = d

        # ── 1. Registrations over last 30 days ──────────────
        today      = datetime.date.today()
        date_range = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
                      for i in range(29, -1, -1)]
        reg_by_day = collections.Counter()
        for r in all_regs:
            day = str(r.get('registered_at', ''))[:10]
            if day in date_range:
                reg_by_day[day] += 1

        regs_over_time = {
            'labels': date_range,
            'data':   [reg_by_day.get(d, 0) for d in date_range],
        }

        # ── 2. Category breakdown ────────────────────────────
        cat_counter = collections.Counter()
        for r in all_regs:
            cat = events_map.get(r.get('event_id', ''), {}).get('category', 'General')
            cat_counter[cat] += 1

        category_breakdown = {
            'labels': list(cat_counter.keys()),
            'data':   list(cat_counter.values()),
        }

        # ── 3. Revenue per event (top 10) ────────────────────
        rev_by_event = collections.defaultdict(int)
        for r in all_regs:
            amount = int(r.get('amount_paid', 0) or 0)
            if amount > 0:
                title = events_map.get(r.get('event_id', ''), {}).get('title', 'Unknown')
                rev_by_event[title] += amount

        sorted_rev = sorted(rev_by_event.items(), key=lambda x: x[1], reverse=True)[:10]
        revenue_per_event = {
            'labels': [i[0] for i in sorted_rev],
            'data':   [i[1] for i in sorted_rev],
        }

        # ── 4. Peak registration hours ───────────────────────
        hour_counter = collections.Counter()
        for r in all_regs:
            raw = str(r.get('registered_at', ''))
            if len(raw) >= 13 and raw[10] == ' ':
                try:
                    hour_counter[int(raw[11:13])] += 1
                except ValueError:
                    pass

        peak_hours = {
            'labels': [f"{h:02d}:00" for h in range(24)],
            'data':   [hour_counter.get(h, 0) for h in range(24)],
        }

        # ── 5. Registrations per event (top 10) ──────────────
        rpe_raw = collections.Counter(r.get('event_id', '') for r in all_regs)
        rpe_sorted = sorted(
            [(events_map.get(eid, {}).get('title', eid[:14]), cnt)
             for eid, cnt in rpe_raw.items()],
            key=lambda x: x[1], reverse=True
        )[:10]
        regs_per_event = {
            'labels': [i[0] for i in rpe_sorted],
            'data':   [i[1] for i in rpe_sorted],
        }

        # ── 6. Free vs paid split ────────────────────────────
        paid_regs = sum(1 for r in all_regs if int(r.get('amount_paid', 0) or 0) > 0)
        free_regs = len(all_regs) - paid_regs

        stats = {
            'total_regs':    len(all_regs),
            'total_revenue': sum(int(r.get('amount_paid', 0) or 0) for r in all_regs),
            'active_events': sum(1 for e in events_map.values() if e.get('status') == 'active'),
            'total_events':  len(events_map),
            'paid_regs':     paid_regs,
            'free_regs':     free_regs,
        }

    except Exception as exc:
        flash(f"Analytics error: {exc}", "danger")
        regs_over_time = category_breakdown = revenue_per_event = {}
        peak_hours = regs_per_event = {}
        stats = {}

    return render_template(
        'admin/analytics.html',
        user_name          = session.get('name'),
        stats              = stats,
        regs_over_time     = json.dumps(regs_over_time),
        category_breakdown = json.dumps(category_breakdown),
        revenue_per_event  = json.dumps(revenue_per_event),
        peak_hours         = json.dumps(peak_hours),
        regs_per_event     = json.dumps(regs_per_event),
    )


# =========================================================
# 3. APPOINT SPOC
# =========================================================
@admin_bp.route('/appoint_spoc', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def appoint_spoc():
    try:
        name     = request.form.get('name',     '').strip()
        email    = request.form.get('email',    '').lower().strip()
        password = request.form.get('password', '').strip()
        category = request.form.get('category', 'General').strip()

        if not name or not email or not password:
            flash("All fields are required.", "warning")
            return redirect('/admin/dashboard')

        if db.collection('users').document(email).get().exists:
            flash(f"A user with email {email} already exists.", "warning")
            return redirect('/admin/dashboard')

        db.collection('users').document(email).set({
            'email':               email,
            'name':                name,
            'role':                'ClubSPOC',
            'category':            category,
            'password':            generate_password_hash(password),
            'created_at':          datetime.datetime.now().strftime("%Y-%m-%d"),
            'needs_password_reset': True
        })
        send_credentials_email(email, name, f'Club SPOC ({category} Division)',
                               password, category)
        log_action(db, "SPOC_APPOINTED",
                   f"{email} appointed as ClubSPOC ({category}) by {session.get('user_id')}")
        flash(f"✅ SPOC account created for {name} ({category}). Credentials emailed.", "success")
    except Exception as exc:
        flash(f"Error appointing SPOC: {exc}", "danger")
    return redirect('/admin/dashboard')


# =========================================================
# 4. DELETE USER
# =========================================================
@admin_bp.route('/delete_user/<email>', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def delete_user(email):
    try:
        db.collection('users').document(email).delete()
        log_action(db, "USER_DELETED",
                   f"User {email} deleted by {session.get('user_id')}")
        flash(f"User {email} deleted.", "warning")
    except Exception as exc:
        flash(f"Delete error: {exc}", "danger")
    return redirect('/admin/dashboard')


# =========================================================
# 5. VIEW AUDIT LOG
# =========================================================
@admin_bp.route('/audit_log')
@login_required
@role_required(SUPER_ROLES)
def view_audit_log():
    try:
        logs = (db.collection('audit_log')
                  .order_by('timestamp', direction=firestore.Query.DESCENDING)
                  .limit(100).stream())
        entries = [l.to_dict() for l in logs]
    except Exception as exc:
        flash(f"Error loading audit log: {exc}", "danger")
        entries = []
    return render_template('admin/audit_log.html', entries=entries)