import collections
import datetime
import json
import re
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, jsonify
try:
    from google.cloud import firestore
except ImportError:
    firestore = None
from werkzeug.security import generate_password_hash

class DynamicDBProxy:
    def __getattr__(self, name):
        try:
            import app as app_module
            if hasattr(app_module, 'db') and app_module.db is not None:
                return getattr(app_module.db, name)
        except Exception:
            pass
        try:
            from models import db as models_db
            return getattr(models_db, name)
        except Exception:
            raise AttributeError(f"No DB available for attribute '{name}'")

db = DynamicDBProxy()
from utils import login_required, role_required, log_action
from utils_email import send_credentials_email

admin_bp    = Blueprint('admin', __name__, url_prefix='/admin')
SUPER_ROLES = ['SuperAdmin', 'Super Admin', 'UniversityAdmin']


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
        events          = []
        total_regs      = 0
        total_revenue   = 0
        unique_staff_emails = set()
        cat_counts      = {}

        for e in events_ref:
            d       = e.to_dict()
            d['id'] = e.id
            rc = int(d.get('registration_count', 0) or 0)
            total_regs += rc
            # Revenue: fee × confirmed registrations
            fee = int((d.get('fees') or {}).get('regular', 0) or d.get('entry_fee', 0) or 0)
            total_revenue += fee * rc
            # Unique staff (deduplicate across events)
            for s in d.get('staff', []):
                if s.get('email'):
                    unique_staff_emails.add(s['email'])
            cat = d.get('category', 'Other')
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            regs = db.collection('registrations').where('event_id', '==', e.id).stream()
            d['scored_teams'] = sum(
                1 for r in regs
                if not r.to_dict().get('is_eliminated', False)
                and r.to_dict().get('scores')
            )
            events.append(d)

        # User stats — role breakdown
        user_stats = {'total': 0, 'students': 0, 'judges': 0,
                      'coordinators': 0, 'spocs': 0, 'admins': 0}
        for u in db.collection('users').stream():
            ud = u.to_dict()
            role = (ud.get('role') or '').strip()
            user_stats['total'] += 1
            if role == 'Student':
                user_stats['students'] += 1
            elif role == 'Judge':
                user_stats['judges'] += 1
            elif role in ('EventCoordinator', 'Coordinator'):
                user_stats['coordinators'] += 1
            elif role == 'ClubSPOC':
                user_stats['spocs'] += 1
            elif role in ('SuperAdmin', 'Super Admin', 'Admin'):
                user_stats['admins'] += 1

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
        events, total_regs, total_revenue = [], 0, 0
        unique_staff_emails, user_stats, audit_log, cat_counts = set(), {}, [], {}

    return render_template(
        'admin/dashboard.html',
        events=events,
        total_regs=total_regs,
        total_revenue=total_revenue,
        total_staff=len(unique_staff_emails),
        user_stats=user_stats,
        cat_counts=cat_counts,
        audit_log=audit_log,
        user_name=session.get('name'),
        today=datetime.date.today().strftime('%Y-%m-%d'),
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
    import csv
    import io
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
            regs = db.collection('registrations') \
                     .where('event_id', '==', event_id).stream()
            seen = set()
            for r in regs:
                d = r.to_dict()
                addr = d.get('lead_email') or d.get('email', '')
                if addr:
                    seen.add(addr.lower().strip())
            emails = list(seen)

        elif audience == 'role_filter' and role_filter:
            users = db.collection('users') \
                      .where('role', '==', role_filter).stream()
            for u in users:
                d = u.to_dict()
                addr = d.get('email') or u.id  # doc ID == email in this system
                if addr:
                    emails.append(addr.lower().strip())

        else:
            users = db.collection('users').stream()
            for u in users:
                d = u.to_dict()
                addr = d.get('email') or u.id
                if addr:
                    emails.append(addr.lower().strip())

        emails = [e for e in emails if e and '@' in e]

        if not emails:
            flash('No recipients found for that selection.', 'warning')
            return render_template('admin/send_email.html', events=events)

        # Send individually and count successes
        from utils_email import _html_wrapper, _send
        import utils_email as _ue
        html_body = _html_wrapper(
            f'<div style="color:#475569;font-size:14px;line-height:1.8;'
            f'white-space:pre-line;">{message}</div>',
            subject
        )
        sent_ok, sent_fail = 0, 0
        failed_addrs = []
        for addr in emails:
            _ue.LAST_EMAIL_ERROR = ''
            if _send(addr, subject, html_body):
                sent_ok += 1
            else:
                sent_fail += 1
                failed_addrs.append(addr)
                current_app.logger.warning(
                    "Bulk email failed → %s | %s", addr, _ue.LAST_EMAIL_ERROR)

        log_action(db, 'BULK_EMAIL_SENT',
                   f"{session.get('user_id')} → ok={sent_ok} fail={sent_fail} | {subject}")

        if sent_ok == 0:
            err = _ue.LAST_EMAIL_ERROR or 'Unknown error — check server logs'
            flash(f'❌ All {sent_fail} emails failed to send. Error: {err}', 'danger')
        elif sent_fail:
            flash(f'⚠️ Sent to {sent_ok} recipient(s). Failed: {sent_fail} '
                  f'({", ".join(failed_addrs[:5])}{"…" if len(failed_addrs)>5 else ""})',
                  'warning')
        else:
            flash(f'✅ Email delivered to {sent_ok} recipient(s).', 'success')

        return render_template('admin/send_email.html',
                               events=events,
                               last_sent={'count': sent_ok, 'subject': subject,
                                          'audience': audience})

    except Exception as exc:
        current_app.logger.exception("Bulk email route error: %s", exc)
        flash(f'Send failed: {exc}', 'danger')
        return render_template('admin/send_email.html', events=events)


# =========================================================
# A4 PORTAL REPORT
# =========================================================
@admin_bp.route('/report')
@login_required
@role_required(SUPER_ROLES)
def report():
    try:
        all_events = []
        total_regs = total_revenue = 0
        cat_counts = {}
        unique_staff = set()

        for e in db.collection('events').order_by('date').stream():
            d = e.to_dict()
            d['id'] = e.id
            rc  = int(d.get('registration_count', 0) or 0)
            fee = int((d.get('fees') or {}).get('regular', 0) or d.get('entry_fee', 0) or 0)
            d['_fee'] = fee
            d['_revenue'] = fee * rc
            total_regs    += rc
            total_revenue += fee * rc
            cat = d.get('category', 'Other')
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            for s in d.get('staff', []):
                if s.get('email'):
                    unique_staff.add(s['email'])
            all_events.append(d)

        user_stats = {'total': 0, 'students': 0, 'judges': 0,
                      'coordinators': 0, 'spocs': 0}
        all_users = []
        for u in db.collection('users').stream():
            ud = u.to_dict()
            role = (ud.get('role') or '').strip()
            user_stats['total'] += 1
            if role == 'Student':
                user_stats['students'] += 1
            elif role == 'Judge':
                user_stats['judges'] += 1
                all_users.append(ud)
            elif role in ('EventCoordinator', 'Coordinator'):
                user_stats['coordinators'] += 1
                all_users.append(ud)
            elif role == 'ClubSPOC':
                user_stats['spocs'] += 1
                all_users.append(ud)

    except Exception as exc:
        flash(f"Report error: {exc}", "danger")
        return redirect('/admin/dashboard')

    return render_template(
        'admin/report.html',
        events=all_events,
        user_stats=user_stats,
        staff_users=all_users,
        total_regs=total_regs,
        total_revenue=total_revenue,
        total_staff=len(unique_staff),
        cat_counts=cat_counts,
        generated_at=datetime.datetime.now().strftime('%d %B %Y, %I:%M %p'),
        today=datetime.date.today().strftime('%d %B %Y'),
    )


# =========================================================
# 5. ORG UNITS & ROLE ASSIGNMENTS MANAGEMENT
# =========================================================
@admin_bp.route('/org_units')
@login_required
@role_required(SUPER_ROLES)
def manage_org_units():
    try:
        units_stream = list(db.collection('org_units').stream())
        units = []
        for u in units_stream:
            d = u.to_dict() or {}
            d['id'] = u.id
            units.append(d)

        # If no units yet, auto-seed default units
        if not units:
            from services_permission import migrate_roles_and_units
            migrate_roles_and_units(db)
            units = [dict(u.to_dict() or {}, id=u.id) for u in db.collection('org_units').stream()]

        roles_stream = list(db.collection('role_assignments').stream())
        role_assignments = []
        for r in roles_stream:
            d = r.to_dict() or {}
            d['id'] = r.id
            role_assignments.append(d)

        # Pending approval events
        pending_events = []
        for e in db.collection('events').stream():
            d = e.to_dict() or {}
            d['id'] = e.id
            if (d.get('status') or '').lower() == 'pending_approval':
                pending_events.append(d)

        users = []
        for u in db.collection('users').stream():
            d = u.to_dict() or {}
            d['id'] = u.id
            users.append(d)

        all_events = []
        for e in db.collection('events').stream():
            d = e.to_dict() or {}
            d['id'] = e.id
            all_events.append(d)

        return render_template(
            'admin/org_units.html',
            units=units,
            role_assignments=role_assignments,
            pending_events=pending_events,
            users=users,
            events=all_events,
            user_name=session.get('name'),
        )
    except Exception as exc:
        flash(f"Error loading org units: {exc}", "danger")
        return redirect('/admin/dashboard')


@admin_bp.route('/org_units/create', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def create_org_unit():
    import re
    import uuid
    try:
        name = request.form.get('name', '').strip()
        unit_type = request.form.get('type', 'department').strip().lower()
        slug = request.form.get('slug', '').strip().lower()
        parent_id = request.form.get('parent_id', 'central').strip() or 'central'

        if not name:
            flash("Unit name is required.", "warning")
            return redirect('/admin/org_units')

        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        unit_id = slug or str(uuid.uuid4())[:8]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        db.collection('org_units').document(unit_id).set({
            'id': unit_id,
            'organization_id': 'default',
            'parent_id': parent_id if parent_id != 'none' else None,
            'type': unit_type,
            'name': name,
            'slug': slug,
            'created_at': now_iso,
            'updated_at': now_iso,
        })
        log_action(db, "ORG_UNIT_CREATED", f"Unit {name} ({unit_type}) created by {session.get('user_id')}")
        flash(f"✅ Unit '{name}' created successfully.", "success")
    except Exception as exc:
        flash(f"Error creating unit: {exc}", "danger")
    return redirect('/admin/org_units')


@admin_bp.route('/roles/assign', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def assign_role():
    try:
        user_id = request.form.get('user_id', '').lower().strip()
        role = request.form.get('role', '').strip()
        scope_type = request.form.get('scope_type', 'university').strip().lower()
        scope_id = request.form.get('scope_id', '').strip()

        if not user_id or not role:
            flash("User email and role are required.", "warning")
            return redirect('/admin/org_units')

        if scope_type == 'university' and not scope_id:
            scope_id = 'default'

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_user = user_id.replace('@', '_').replace('.', '_')
        clean_scope = scope_id.replace('@', '_').replace('.', '_')
        ra_id = f"ra_{clean_user}_{scope_type}_{clean_scope}"

        db.collection('role_assignments').document(ra_id).set({
            'id': ra_id,
            'user_id': user_id,
            'role': role,
            'scope_type': scope_type,
            'scope_id': scope_id,
            'created_at': now_iso,
        })

        # Update user record role if exists
        try:
            udoc = db.collection('users').document(user_id)
            if udoc.get().exists:
                udoc.update({'role': role})
        except Exception:
            pass

        log_action(db, "ROLE_ASSIGNED", f"Role {role} ({scope_type}:{scope_id}) assigned to {user_id} by {session.get('user_id')}")
        flash(f"✅ Assigned {role} to {user_id} ({scope_type}: {scope_id}).", "success")
    except Exception as exc:
        flash(f"Error assigning role: {exc}", "danger")
    return redirect('/admin/org_units')


@admin_bp.route('/roles/revoke/<assignment_id>', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def revoke_role(assignment_id):
    try:
        db.collection('role_assignments').document(assignment_id).delete()
        log_action(db, "ROLE_REVOKED", f"Role assignment {assignment_id} revoked by {session.get('user_id')}")
        flash("✅ Role assignment revoked.", "success")
    except Exception as exc:
        flash(f"Error revoking role: {exc}", "danger")
    return redirect('/admin/org_units')


@admin_bp.route('/events/approve/<event_id>', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def approve_event(event_id):
    try:
        from services_workflow import WorkflowEngine
        WorkflowEngine.transition_event(
            db,
            event_id=event_id,
            target_state='published',
            actor_id=session.get('user_id'),
            actor=session,
            metadata={'source': 'admin_approval'}
        )
        flash("✅ Event approved and published!", "success")
    except Exception as exc:
        flash(f"Approval error: {exc}", "danger")
    return redirect('/admin/org_units')


@admin_bp.route('/migrate_roles', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def trigger_role_migration():
    try:
        from services_permission import migrate_roles_and_units
        result = migrate_roles_and_units(db)
        flash(f"✅ Migration complete: {len(result.get('migrated_admins', []))} Admins, {len(result.get('migrated_spocs', []))} UnitAdmins, {len(result.get('backfilled_events', []))} Events backfilled.", "success")
        if result.get('unmapped_users'):
            flash(f"⚠️ Unmapped users: {[u['email'] for u in result['unmapped_users']]}", "warning")
    except Exception as exc:
        flash(f"Migration error: {exc}", "danger")
    return redirect('/admin/org_units')


# =========================================================
# 19. VENUES & ROOM MANAGEMENT (Campus -> Building -> Room)
# =========================================================

@admin_bp.route('/venues', methods=['GET'])
@login_required
@role_required(SUPER_ROLES)
def list_venues():
    try:
        from services_venue import format_kolkata
        campuses = [c.to_dict() for c in db.collection('campuses').stream()]
        buildings = [b.to_dict() for b in db.collection('buildings').stream()]
        rooms = [r.to_dict() for r in db.collection('rooms').stream()]
        bookings = [b.to_dict() for b in db.collection('venue_bookings').stream()]

        # Enrich bookings with room name and human time
        room_map = {r.get('id'): r.get('name') for r in rooms}
        for b in bookings:
            b['room_name'] = room_map.get(b.get('room_id') or b.get('roomId'), b.get('room_id') or b.get('roomId'))
            b['start_ist'] = format_kolkata(b.get('start_time') or b.get('startTime'))
            b['end_ist'] = format_kolkata(b.get('end_time') or b.get('endTime'))

        # Return JSON if requested
        if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
            return jsonify({
                'campuses': campuses,
                'buildings': buildings,
                'rooms': rooms,
                'bookings': bookings,
            })

        return render_template(
            'admin/venues.html',
            campuses=campuses,
            buildings=buildings,
            rooms=rooms,
            bookings=bookings,
        )
    except Exception as exc:
        current_app.logger.error("Error loading venues: %s", exc)
        flash(f"Error loading venues: {exc}", "danger")
        return redirect('/admin/dashboard')


@admin_bp.route('/venues/seed', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def seed_venues_route():
    try:
        from services_venue import seed_default_venues
        counts = seed_default_venues(db)
        flash(f"✅ Venues seeded: {counts.get('campuses', 0)} campuses, {counts.get('buildings', 0)} buildings, {counts.get('rooms', 0)} rooms.", "success")
    except Exception as exc:
        flash(f"Error seeding venues: {exc}", "danger")
    return redirect('/admin/venues')


@admin_bp.route('/venues/campus/create', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def create_campus():
    try:
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        address = request.form.get('address', '').strip()

        if not name:
            flash("Campus name is required.", "warning")
            return redirect('/admin/venues')

        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        campus_id = slug or f"campus_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        db.collection('campuses').document(campus_id).set({
            'id': campus_id,
            'organization_id': 'default',
            'name': name,
            'slug': slug,
            'address': address,
            'created_at': now_iso,
            'updated_at': now_iso,
        })
        log_action(db, "CAMPUS_CREATED", f"Campus {name} created by {session.get('user_id')}")
        flash(f"✅ Campus '{name}' created successfully.", "success")
    except Exception as exc:
        flash(f"Error creating campus: {exc}", "danger")
    return redirect('/admin/venues')


@admin_bp.route('/venues/building/create', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def create_building():
    try:
        campus_id = request.form.get('campus_id', '').strip()
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()

        if not campus_id or not name:
            flash("Campus and building name are required.", "warning")
            return redirect('/admin/venues')

        bldg_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        bldg_id = f"bldg_{bldg_slug}" if bldg_slug else f"bldg_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        db.collection('buildings').document(bldg_id).set({
            'id': bldg_id,
            'campus_id': campus_id,
            'name': name,
            'code': code,
            'created_at': now_iso,
            'updated_at': now_iso,
        })
        log_action(db, "BUILDING_CREATED", f"Building {name} created by {session.get('user_id')}")
        flash(f"✅ Building '{name}' created successfully.", "success")
    except Exception as exc:
        flash(f"Error creating building: {exc}", "danger")
    return redirect('/admin/venues')


@admin_bp.route('/venues/room/create', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def create_room():
    try:
        building_id = request.form.get('building_id', '').strip()
        name = request.form.get('name', '').strip()
        room_number = request.form.get('room_number', '').strip()
        capacity = int(request.form.get('capacity', 50) or 50)
        room_type = request.form.get('type', 'classroom').strip().lower()
        facilities_raw = request.form.get('facilities', '').strip()

        if not building_id or not name:
            flash("Building and room name are required.", "warning")
            return redirect('/admin/venues')

        facilities = [f.strip() for f in facilities_raw.split(',') if f.strip()]
        room_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        room_id = f"room_{room_slug}" if room_slug else f"room_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        db.collection('rooms').document(room_id).set({
            'id': room_id,
            'building_id': building_id,
            'name': name,
            'room_number': room_number,
            'capacity': capacity,
            'type': room_type,
            'facilities': facilities,
            'facilities_json': json.dumps(facilities),
            'created_at': now_iso,
            'updated_at': now_iso,
        })
        log_action(db, "ROOM_CREATED", f"Room {name} ({room_type}, cap={capacity}) created by {session.get('user_id')}")
        flash(f"✅ Room '{name}' created successfully.", "success")
    except Exception as exc:
        flash(f"Error creating room: {exc}", "danger")
    return redirect('/admin/venues')


@admin_bp.route('/venues/room/<room_id>/edit', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def edit_room(room_id):
    try:
        doc = db.collection('rooms').document(room_id).get()
        if not doc.exists:
            flash("Room not found.", "danger")
            return redirect('/admin/venues')

        updates = {}
        for f in ['name', 'room_number', 'type']:
            val = request.form.get(f, '').strip()
            if val:
                updates[f] = val

        if request.form.get('capacity'):
            try:
                updates['capacity'] = int(request.form.get('capacity'))
            except (ValueError, TypeError):
                pass

        if 'facilities' in request.form:
            facilities = [f.strip() for f in request.form.get('facilities', '').split(',') if f.strip()]
            updates['facilities'] = facilities
            updates['facilities_json'] = json.dumps(facilities)

        updates['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.collection('rooms').document(room_id).update(updates)
        log_action(db, "ROOM_UPDATED", f"Room {room_id} updated by {session.get('user_id')}")
        flash(f"✅ Room '{room_id}' updated successfully.", "success")
    except Exception as exc:
        flash(f"Error updating room: {exc}", "danger")
    return redirect('/admin/venues')


@admin_bp.route('/venues/room/<room_id>/delete', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def delete_room(room_id):
    try:
        db.collection('rooms').document(room_id).delete()
        log_action(db, "ROOM_DELETED", f"Room {room_id} deleted by {session.get('user_id')}")
        flash(f"✅ Room '{room_id}' deleted successfully.", "success")
    except Exception as exc:
        flash(f"Error deleting room: {exc}", "danger")
    return redirect('/admin/venues')

