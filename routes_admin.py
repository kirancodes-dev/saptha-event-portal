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

        # ── 7. Conversion funnel ─────────────────────────────
        f_registered = len(all_regs)
        f_confirmed  = sum(1 for r in all_regs if r.get('status') == 'Confirmed')
        f_attended   = sum(1 for r in all_regs if r.get('attendance') == 'Present')
        f_certified  = sum(
            1 for r in all_regs
            if r.get('attendance') == 'Present'
            and events_map.get(r.get('event_id', ''), {}).get('status') == 'completed'
        )
        funnel = {
            'labels': ['Registered', 'Confirmed', 'Attended', 'Certified'],
            'data':   [f_registered, f_confirmed, f_attended, f_certified],
        }

        # ── 8. No-show rate per completed event (top 10) ─────
        no_show_rows = []
        for eid, evt in events_map.items():
            if evt.get('status') != 'completed':
                continue
            evt_regs = [r for r in all_regs if r.get('event_id') == eid]
            if not evt_regs:
                continue
            attended = sum(1 for r in evt_regs if r.get('attendance') == 'Present')
            total    = len(evt_regs)
            rate     = round((total - attended) * 100 / total, 1) if total else 0
            no_show_rows.append({
                'title':       evt.get('title', eid[:14]),
                'total':       total,
                'attended':    attended,
                'no_show':     total - attended,
                'rate':        rate,
            })
        no_show_rows.sort(key=lambda x: x['rate'], reverse=True)
        no_show_rows = no_show_rows[:10]
        no_show_chart = {
            'labels': [row['title'] for row in no_show_rows],
            'data':   [row['rate']  for row in no_show_rows],
        }

        stats = {
            'total_regs':    len(all_regs),
            'total_revenue': sum(int(r.get('amount_paid', 0) or 0) for r in all_regs),
            'active_events': sum(1 for e in events_map.values() if e.get('status') == 'active'),
            'total_events':  len(events_map),
            'paid_regs':     paid_regs,
            'free_regs':     free_regs,
            'attended':      f_attended,
            'no_show_pct':   round((f_confirmed - f_attended) * 100 / f_confirmed, 1) if f_confirmed else 0,
            'conv_pct':      round(f_attended * 100 / f_registered, 1) if f_registered else 0,
        }

    except Exception as exc:
        flash(f"Analytics error: {exc}", "danger")
        regs_over_time = category_breakdown = revenue_per_event = {}
        peak_hours = regs_per_event = funnel = no_show_chart = {}
        no_show_rows = []
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
        funnel             = json.dumps(funnel),
        no_show_chart      = json.dumps(no_show_chart),
        no_show_rows       = no_show_rows,
    )


# =========================================================
# 2b. CSV EXPORT — analytics / registrations
# =========================================================
@admin_bp.route('/analytics/export/<kind>')
@login_required
@role_required(SUPER_ROLES)
def analytics_export(kind):
    import csv, io
    from flask import Response

    if kind not in ('registrations', 'events', 'revenue'):
        flash("Unknown export type.", "warning")
        return redirect('/admin/analytics')

    events_map = {}
    for e in db.collection('events').stream():
        d = e.to_dict() or {}
        d['id'] = e.id
        events_map[e.id] = d

    buf = io.StringIO()
    writer = csv.writer(buf)

    if kind == 'registrations':
        writer.writerow([
            'reg_id', 'event_title', 'lead_name', 'lead_email', 'lead_usn',
            'team_name', 'member_count', 'status', 'payment_status',
            'amount_paid', 'attendance', 'final_rank', 'final_score', 'registered_at'
        ])
        for r in db.collection('registrations').stream():
            d = r.to_dict() or {}
            writer.writerow([
                d.get('reg_id', r.id),
                d.get('event_title', events_map.get(d.get('event_id', ''), {}).get('title', '')),
                d.get('lead_name', ''),
                d.get('lead_email', ''),
                d.get('lead_usn', ''),
                d.get('team_name', ''),
                d.get('member_count', 1),
                d.get('status', ''),
                d.get('payment_status', ''),
                d.get('amount_paid', 0),
                d.get('attendance', ''),
                d.get('final_rank', ''),
                d.get('final_score', ''),
                d.get('registered_at', ''),
            ])
        filename = 'registrations.csv'

    elif kind == 'events':
        writer.writerow(['event_id', 'title', 'category', 'date', 'venue',
                         'status', 'entry_fee', 'registration_count'])
        for eid, e in events_map.items():
            writer.writerow([
                eid, e.get('title', ''), e.get('category', ''),
                e.get('date', ''), e.get('venue', ''), e.get('status', ''),
                e.get('entry_fee', 0), e.get('registration_count', 0),
            ])
        filename = 'events.csv'

    else:  # revenue
        by_event = collections.defaultdict(lambda: {'count': 0, 'revenue': 0})
        for r in db.collection('registrations').stream():
            d = r.to_dict() or {}
            amt = int(d.get('amount_paid', 0) or 0)
            if amt <= 0:
                continue
            eid = d.get('event_id', '')
            by_event[eid]['count']   += 1
            by_event[eid]['revenue'] += amt
        writer.writerow(['event_id', 'title', 'paid_registrations', 'revenue_inr'])
        for eid, row in sorted(by_event.items(), key=lambda x: x[1]['revenue'], reverse=True):
            writer.writerow([
                eid,
                events_map.get(eid, {}).get('title', eid),
                row['count'],
                row['revenue'],
            ])
        filename = 'revenue.csv'

    log_action(session.get('user_id'), 'analytics_export', kind)
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
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


# =========================================================
# BULK EMAIL — send to all users or all registrants of an event
# =========================================================
@admin_bp.route('/send_email', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def send_bulk_email():
    """
    GET  → show compose form (recipient options + subject + body)
    POST → send to selected audience and show delivery report
    """
    from utils_email import send_broadcast_email

    events = []
    try:
        events = [
            {**e.to_dict(), 'id': e.id}
            for e in db.collection('events').stream()
        ]
    except Exception:
        pass

    if request.method == 'GET':
        return render_template('admin/send_email.html', events=events)

    # ── POST — collect form values ────────────────────────
    audience   = request.form.get('audience', 'all_users')  # all_users | event_regs | role_filter
    event_id   = request.form.get('event_id', '').strip()
    role_filter = request.form.get('role_filter', '').strip()  # Student / Coordinator / Judge / …
    subject    = request.form.get('subject', '').strip()
    message    = request.form.get('message', '').strip()

    if not subject or not message:
        flash('Subject and message are required.', 'warning')
        return render_template('admin/send_email.html', events=events)

    emails = []

    try:
        if audience == 'event_regs' and event_id:
            # All registrants of one event
            regs = db.collection('registrations') \
                     .where('event_id', '==', event_id).stream()
            emails = list({r.to_dict().get('lead_email', '') for r in regs})

        elif audience == 'role_filter' and role_filter:
            # All users with a specific role
            users = db.collection('users') \
                      .where('role', '==', role_filter).stream()
            emails = [u.to_dict().get('email', '') for u in users]

        else:
            # Default: every user in the system
            users = db.collection('users').stream()
            emails = [u.to_dict().get('email', '') for u in users]

        # Strip empty
        emails = [e for e in emails if e and '@' in e]

        if not emails:
            flash('No recipients found for that selection.', 'warning')
            return render_template('admin/send_email.html', events=events)

        ok = send_broadcast_email(emails, subject, message)
        log_action(db, 'BULK_EMAIL_SENT',
                   f"{session.get('user_id')} → {len(emails)} recipients | {subject}")

        flash(f"✅ Email sent to {len(emails)} recipient(s).", 'success')
        return render_template('admin/send_email.html',
                               events=events,
                               last_sent={'count': len(emails), 'subject': subject,
                                          'audience': audience})

    except Exception as exc:
        flash(f'Send failed: {exc}', 'danger')
        return render_template('admin/send_email.html', events=events)