import collections
import csv
import datetime
import io
import json
import logging
import re
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, jsonify
# Newest-first ordering: the SQL layer and Firestore both use this string
# (google.cloud.firestore.Query.DESCENDING == 'DESCENDING').
DESCENDING = 'DESCENDING'

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
from services_accounts import create_unverified_account, send_set_password_link

admin_bp    = Blueprint('admin', __name__, url_prefix='/admin')
logger      = logging.getLogger(__name__)
SUPER_ROLES = ['SuperAdmin', 'Super Admin', 'UniversityAdmin']


# =========================================================
# 1. SUPER ADMIN DASHBOARD
# =========================================================
@admin_bp.route('/dashboard')
@login_required
@role_required(SUPER_ROLES)
def dashboard():
    from services_insights import paid_amount
    try:
        events_ref = (db.collection('events')
                        .order_by('created_at', direction=DESCENDING)
                        .stream())
        events          = []
        total_regs      = 0
        total_revenue   = 0
        unique_staff_emails = set()
        cat_counts      = {}

        for e in events_ref:
            d       = e.to_dict()
            d['id'] = e.id
            # Unique staff (deduplicate across events)
            for s in d.get('staff', []):
                if s.get('email'):
                    unique_staff_emails.add(s['email'])
            cat = d.get('category', 'Other')
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            regs = [r.to_dict() or {} for r in
                    db.collection('registrations').where('event_id', '==', e.id).stream()]
            # Counted from the registrations, not the cached counter, which can
            # be stale; revenue is what was actually paid (UPG-81)
            d['registration_count'] = len(regs)
            total_regs += len(regs)
            total_revenue += sum(paid_amount(r) for r in regs)
            d['scored_teams'] = sum(
                1 for r in regs
                if not r.get('is_eliminated', False) and r.get('scores')
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
                      .order_by('timestamp', direction=DESCENDING)
                      .limit(20).stream())
            audit_log = [l.to_dict() for l in logs]
        except Exception:
            pass

    except Exception as exc:
        flash(f"Dashboard error: {exc}", "danger")
        events, total_regs, total_revenue = [], 0, 0
        unique_staff_emails, user_stats, audit_log, cat_counts = set(), {}, [], {}

    from utils_pagination import paginate_events
    # What needs the Super Admin's attention (UPG-75)
    statuses = collections.Counter(str(e.get('status') or 'active').lower() for e in events)
    jobs = _outbox_rows() or []
    attention = {
        'pending': statuses.get('pending_approval', 0),
        'drafts': statuses.get('draft', 0),
        'failed_jobs': sum(1 for j in jobs if j['status'] == 'failed'),
        'inactive': sum(1 for d in db.collection('users').stream() if (d.to_dict() or {}).get('is_active') is False),
    }
    return render_template(
        'admin/dashboard.html',
        attention=attention,
        events=events,
        page=paginate_events(events),   # the table shows 25 a page; stats and charts use every event (UPG-19)
        status_filter=(request.args.get('status') or '').strip().lower(),
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
    """Every event's figures, with period and category filters (UPG-83)."""
    from services_insights import build
    events = []
    for e in db.collection('events').stream():
        d = e.to_dict() or {}
        d['id'] = e.id
        events.append(d)
    regs = [r.to_dict() or {} for r in db.collection('registrations').stream()]
    data = build(events, regs, period=request.args.get('period', '30'),
                 category=(request.args.get('category') or '').strip())
    return render_template('analytics/hub.html', data=data, scope='admin', action_url='/admin/analytics')


# =========================================================
# 2b. CSV EXPORT — analytics / registrations
# =========================================================
@admin_bp.route('/analytics/export/<kind>')
@login_required
def analytics_export(kind):
    import csv
    import io
    from flask import Response, abort

    if session.get('role') not in SUPER_ROLE_NAMES:
        abort(403)  # every registration of every event: Super Admins only (UPG-03)
    if kind not in ('registrations', 'events', 'revenue', 'payments'):
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
        import services_export
        buf.write(services_export.to_csv(services_export.all_registration_rows(db),
                                         ['Event'] + services_export.COLUMNS))
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

    elif kind == 'payments':  # one row per Razorpay order, for the finance office (UPG-30)
        from services_payments import all_orders
        writer.writerow(['order_id', 'payment_id', 'event_id', 'event_title', 'email', 'amount_inr', 'status',
                         'reg_id', 'paid_at', 'refund_id', 'refunded_at', 'note'])
        for o in all_orders():
            writer.writerow([o['id'], o['payment_id'], o['event_id'], events_map.get(o['event_id'], {}).get('title', ''),
                             o['email'], o['amount_paise'] / 100, o['status'], o['reg_id'], o['paid_at'] or '',
                             o['refund_id'], o['refunded_at'] or '', o['failure_reason']])
        filename = 'payments.csv'

    elif kind in ('activity', 'activity_points', 'department_activity'):
        import services_export
        dept = request.args.get('department')
        buf.write(services_export.department_activity_csv(db, dept, request.args.get('participant_type')))
        filename = f"activity_ledger_{dept or 'all'}.csv"

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


@admin_bp.route('/export/department_activity')
@admin_bp.route('/export/activity_points')
@login_required
@role_required(SUPER_ROLES)
def export_department_activity():
    dept = request.args.get('department')
    fmt = request.args.get('format', 'csv').lower()
    from flask import Response
    import services_export
    if fmt == 'xlsx':
        data = services_export.department_activity_xlsx(db, dept, request.args.get('participant_type'))
        return Response(
            data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="activity_ledger_{dept or "all"}.xlsx"'}
        )
    data = services_export.department_activity_csv(db, dept, request.args.get('participant_type'))
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="activity_ledger_{dept or "all"}.csv"'}
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
        category = request.form.get('category', 'General').strip()

        if not name or not email:
            flash("All fields are required.", "warning")
            return redirect('/admin/dashboard')

        if db.collection('users').document(email).get().exists:
            flash(f"A user with email {email} already exists.", "warning")
            return redirect('/admin/dashboard')

        # The new SPOC chooses their own password through a one-time link;
        # nobody types or emails one (UPG-33)
        create_unverified_account(db, email, name, role='ClubSPOC', category=category)
        send_set_password_link(db, email, name,
                               reason=f"when you were appointed as Club SPOC ({category} division)")
        log_action(db, "SPOC_APPOINTED",
                   f"{email} appointed as ClubSPOC ({category}) by {session.get('user_id')}")
        flash(f"✅ SPOC account created for {name} ({category}). A link to set their password was emailed.", "success")
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
    if email.strip().lower() == (session.get('user_id') or '').lower():
        flash("You can't delete your own account.", "danger")   # UPG-75
        return redirect('/admin/users')
    try:
        db.collection('users').document(email).delete()
        log_action(db, "USER_DELETED",
                   f"User {email} deleted by {session.get('user_id')}")
        flash(f"User {email} deleted.", "warning")
    except Exception as exc:
        flash(f"Delete error: {exc}", "danger")
    return redirect('/admin/users')


# =========================================================
# 4b. USERS — who still has to set a password; resend their link (UPG-40)
# =========================================================
SUPER_ROLE_NAMES = {'SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin'}


def _role_name(user: dict) -> str:
    role = user.get('role') or ''
    return str(getattr(role, 'value', role))


def _waiting_for_password(user: dict) -> bool:
    # Accounts someone else creates stay locked until the set-password link
    # is used (UPG-33); using it, or a reset, clears the flag.
    return bool(user.get('needs_password_reset'))


@admin_bp.route('/users')
@login_required
@role_required(SUPER_ROLES)
def users():
    from utils_pagination import page_args, paginate_items, paginate_query

    def account(doc):
        u = doc.to_dict() or {}
        role = _role_name(u)
        waiting = _waiting_for_password(u)
        return {
            'email':      doc.id,
            'name':       u.get('name', ''),
            'usn':        u.get('usn', ''),
            'department': u.get('department', ''),
            'year':       u.get('year', ''),
            'section':    u.get('section', ''),
            'role':       role,
            'waiting':    waiting,
            'can_resend': waiting and role not in SUPER_ROLE_NAMES,
            'active':     u.get('is_active', True) is not False,   # UPG-75
        }

    # A role filter (UPG-75) loads and filters like a search
    role_filter = (request.args.get('role') or '').strip()
    if role_filter:
        accounts = sorted((a for a in (account(d) for d in db.collection('users').stream())
                           if a['role'] == role_filter or (role_filter == 'inactive' and not a['active'])),
                          key=lambda a: a['email'])
        page = paginate_items(accounts, search_fields=('name', 'email', 'usn', 'department', 'role'))
        return render_template('admin/users.html', accounts=page.items, page=page, current_page='users',
                               roles=ASSIGNABLE_ROLES, categories=SPOC_CATEGORIES, role_filter=role_filter)

    # 25 a page in email order, paged in SQL; a search loads and filters (UPG-19).
    if page_args()[2]:
        accounts = sorted((account(d) for d in db.collection('users').stream()), key=lambda a: a['email'])
        page = paginate_items(accounts, search_fields=('name', 'email', 'usn', 'department', 'role'))
    else:
        page = paginate_query(db.collection('users').order_by('email'), transform=account)
    return render_template('admin/users.html', accounts=page.items, page=page, current_page='users',
                           roles=ASSIGNABLE_ROLES, categories=SPOC_CATEGORIES, role_filter='')


@admin_bp.route('/users/import_csv', methods=['POST'])
@admin_bp.route('/students/import_csv', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def import_student_roster():
    file = request.files.get('file') or request.files.get('csv_file')
    csv_text = ''
    if file and file.filename:
        raw = file.read()
        try:
            csv_text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_text = raw.decode('latin-1')
    else:
        csv_text = request.form.get('csv_data', '')

    if not csv_text.strip():
        flash("Please select a valid CSV file to upload.", "warning")
        return redirect('/admin/users')

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        flash("CSV file is empty or missing a header row.", "danger")
        return redirect('/admin/users')

    created_count = 0
    updated_count = 0

    for row in reader:
        norm = {
            k.strip().lower().replace(' ', '_'): (v or '').strip()
            for k, v in row.items() if k
        }
        email = (
            norm.get('email')
            or norm.get('email_id')
            or norm.get('student_email')
            or norm.get('mail')
            or ''
        ).lower()
        if not email or '@' not in email:
            continue

        name = (
            norm.get('name')
            or norm.get('student_name')
            or norm.get('full_name')
            or ''
        )
        usn = (
            norm.get('usn')
            or norm.get('roll_no')
            or norm.get('roll_number')
            or norm.get('rollno')
            or norm.get('reg_no')
            or norm.get('registration_no')
            or ''
        )
        department = (
            norm.get('department')
            or norm.get('dept')
            or norm.get('branch')
            or ''
        )
        year = (
            norm.get('year')
            or norm.get('class_year')
            or norm.get('batch')
            or ''
        )
        section = (
            norm.get('section')
            or norm.get('sec')
            or ''
        )
        # Academic record for placement drives (UPG-57): only the roster sets these
        academics = {}
        cgpa_raw = norm.get('cgpa') or norm.get('gpa') or ''
        backlogs_raw = norm.get('backlogs') or norm.get('active_backlogs') or ''
        try:
            if cgpa_raw:
                academics['cgpa'] = round(float(cgpa_raw), 2)
            if backlogs_raw:
                academics['backlogs'] = int(float(backlogs_raw))
        except ValueError:
            pass

        doc_ref = db.collection('users').document(email)
        user_doc = doc_ref.get()

        if user_doc.exists:
            update_data = {}
            if name:
                update_data['name'] = name
            if usn:
                update_data['usn'] = usn
            if department:
                update_data['department'] = department
            if year:
                update_data['year'] = year
            if section:
                update_data['section'] = section
            update_data.update(academics)
            if update_data:
                doc_ref.set(update_data, merge=True)
            updated_count += 1
        else:
            create_unverified_account(
                db,
                email=email,
                name=name or email.split('@')[0],
                role='Student',
                usn=usn,
                department=department,
                year=year,
                section=section,
                **academics,
            )
            created_count += 1

    log_action(db, "STUDENT_ROSTER_IMPORTED",
               f"Roster imported: {created_count} created, {updated_count} updated by {session.get('user_id')}")
    flash(f"✅ Student roster imported: {created_count} created, {updated_count} updated.", "success")
    return redirect('/admin/users')


@admin_bp.route('/users/<path:email>/academics', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def edit_academics(email):
    """An admin corrects a student's CGPA and active backlogs (UPG-57); students
    see them on their profile but can't change them."""
    email = email.strip().lower()
    doc = db.collection('users').document(email).get()
    if not doc.exists:
        flash("No account with that email.", "warning")
        return redirect('/admin/users')
    user = doc.to_dict() or {}
    if request.method == 'POST':
        updates, problems = {}, []
        cgpa, backlogs = request.form.get('cgpa', '').strip(), request.form.get('backlogs', '').strip()
        try:
            if cgpa:
                value = float(cgpa)
                if not 0 <= value <= 10:
                    raise ValueError
                updates['cgpa'] = round(value, 2)
        except ValueError:
            problems.append("CGPA must be a number from 0 to 10.")
        try:
            if backlogs:
                value = int(backlogs)
                if value < 0:
                    raise ValueError
                updates['backlogs'] = value
        except ValueError:
            problems.append("Backlogs must be a whole number, 0 or more.")
        if problems:
            for p in problems:
                flash(p, "danger")
        elif updates:
            db.collection('users').document(email).set(updates, merge=True)
            log_action(db, "ACADEMIC_RECORD_UPDATED", f"{session.get('user_id')} set {updates} for {email}")
            flash("Academic record saved.", "success")
            return redirect('/admin/users?q=' + email)
    return render_template('admin/user_academics.html', email=email, user=user, current_page='users')


@admin_bp.route('/users/resend_set_password', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def resend_set_password():
    email = request.form.get('email', '').strip().lower()
    doc = db.collection('users').document(email).get() if email else None
    user = (doc.to_dict() or {}) if doc is not None and doc.exists else None

    if user is None:
        flash("No account with that email.", "warning")
    elif _role_name(user) in SUPER_ROLE_NAMES:
        flash("Set-password links can't be sent for Super Admin accounts.", "danger")
    elif not _waiting_for_password(user):
        flash(f"{email} has already set a password. If they've lost it, they can use \"Forgot password\".", "warning")
    elif send_set_password_link(db, email, user.get('name', ''),
                                reason="earlier, and an administrator has sent you a new link"):
        log_action(db, "SET_PASSWORD_LINK_RESENT",
                   f"Set-password link resent to {email} by {session.get('user_id')}")
        flash(f"✅ A new set-password link was emailed to {email}.", "success")
    else:
        flash(f"The email to {email} couldn't be sent. Check the mail settings and try again.", "danger")
    return redirect('/admin/users')


# =========================================================
# 4c. PAYMENTS — refunds, cancellations, payments with no registration (UPG-30)
# =========================================================
def _super_only():
    from flask import abort
    if session.get('role') not in SUPER_ROLE_NAMES:
        abort(403)


def _is_paid(reg):
    return (float(reg.get('amount_paid') or 0) > 0
            or str(reg.get('payment_status') or '').lower().startswith(('paid', 'refunded')))


@admin_bp.route('/payments')
@login_required
def payments():
    _super_only()
    from services_payments import unmatched_orders
    titles = {e.id: (e.to_dict() or {}).get('title', '') for e in db.collection('events').stream()}
    orders = [dict(o, event_title=titles.get(o['event_id'], o['event_id']), amount=o['amount_paise'] / 100)
              for o in unmatched_orders()]
    regs = sorted(([d.id, d.to_dict() or {}] for d in db.collection('registrations').stream()),
                  key=lambda r: str(r[1].get('registered_at') or ''), reverse=True)
    paid = [dict(r, doc_id=rid, event_title=titles.get(str(r.get('event_id')), r.get('event_title', '')))
            for rid, r in regs if _is_paid(r)]
    from utils_pagination import paginate_items
    page = paginate_items(paid, search_fields=('lead_name', 'lead_email', 'usn', 'reg_id', 'event_title'))
    # Cancelled events that still hold payments: refund them all (UPG-51)
    statuses = {e.id: str((e.to_dict() or {}).get('status', '')).lower() for e in db.collection('events').stream()}
    cancelled_paid = collections.Counter(str(r.get('event_id')) for r in paid
                                         if statuses.get(str(r.get('event_id'))) == 'cancelled'
                                         and str(r.get('payment_status') or '').lower() != 'refunded')
    cancelled_events = [{'id': eid, 'title': titles.get(eid, eid), 'count': n} for eid, n in cancelled_paid.items()]
    return render_template('admin/payments.html', orders=orders, registrations=page.items, page=page,
                           cancelled_events=cancelled_events, current_page='payments')


@admin_bp.route('/payments/orders')
@login_required
def payment_orders():
    """Every recent Razorpay order with its status, for reconciliation; the
    CSV has all of them (UPG-94)."""
    _super_only()
    from services_payments import all_orders
    titles = {e.id: (e.to_dict() or {}).get('title', '') for e in db.collection('events').stream()}
    recent = [dict(o, event_title=titles.get(o['event_id'], o['event_id']), amount=o['amount_paise'] / 100,
                   registration=o['reg_id'] or o['reg_data'].get('reg_id', ''))
              for o in reversed(all_orders()[-50:])]
    return render_template('admin/payment_orders.html', recent_orders=recent, current_page='payments')


# =========================================================
# REFUND A CANCELLED EVENT'S PAYMENTS (UPG-51)
# =========================================================
def _refund_event_or_abort(event_id):
    """The event, for a Super Admin or whoever may edit it; 403 for anyone else."""
    from flask import abort
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if session.get('role') not in SUPER_ROLE_NAMES and not can(session, 'edit_event', event, db=db):
        abort(403)
    return event


def _event_refund_rows(event_id):
    """Every paid registration of the event with its Razorpay order, if any."""
    from services_payments import get_order
    rows = []
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        if not _is_paid(reg):
            continue
        order = get_order(reg.get('razorpay_order_id') or '')
        rows.append({'doc_id': doc.id, 'reg': reg, 'order': order,
                     'amount': (order['amount_paise'] / 100) if order else reg.get('amount_paid') or 0,
                     'state': (order['status'] if order else 'no_order')})
    return rows


@admin_bp.route('/events/<event_id>/refunds')
@login_required
def event_refunds(event_id):
    event = _refund_event_or_abort(event_id)
    rows = _event_refund_rows(event_id)
    due = [r for r in rows if r['state'] == 'paid']
    return render_template('admin/event_refunds.html', event=event, rows=rows,
                           due_count=len(due), due_total=sum(float(r['amount'] or 0) for r in due),
                           cancelled=str(event.get('status', '')).lower() == 'cancelled')


@admin_bp.route('/events/<event_id>/refund_all', methods=['POST'])
@login_required
def refund_all(event_id):
    """Refund every paid registration of a cancelled event through Razorpay:
    once per payment (an atomic claim on its order), failures kept with their
    reason for a retry, each refund audit-logged and emailed."""
    from services_payments import finish_refund, refund_failed, start_registration_refund
    event = _refund_event_or_abort(event_id)
    back = f'/admin/events/{event_id}/refunds'
    if str(event.get('status', '')).lower() != 'cancelled':
        flash("Refunds for everyone are only for cancelled events.", "warning")
        return redirect(back)
    if request.form.get('confirm') != 'yes':
        flash("Tick the box to confirm the refunds.", "warning")
        return redirect(back)

    import routes_payment
    actor = session.get('user_id', '')
    done = failed = 0
    for row in _event_refund_rows(event_id):
        if row['state'] != 'paid':
            continue
        order = start_registration_refund(row['order']['id'])
        if order is None:
            continue   # another request is refunding it, or it already was
        try:
            refund = routes_payment._rzp().payment.refund(order['payment_id'], {'amount': order['amount_paise']})
        except Exception as exc:
            refund_failed(order['id'], str(exc))
            logger.warning("Refund failed for order %s: %s", order['id'], exc)
            failed += 1
            continue
        refund_id = str((refund or {}).get('id', ''))
        finish_refund(order['id'], refund_id, actor)
        reg = row['reg']
        db.collection('registrations').document(row['doc_id']).update({
            'payment_status': 'Refunded', 'status': 'cancelled', 'refund_id': refund_id,
            'refunded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'refunded_by': actor,
            'cancel_reason': 'Event cancelled'})
        log_action(db, "PAYMENT_REFUNDED",
                   f"Event {event_id} cancelled: order {order['id']} (payment {order['payment_id']}, "
                   f"₹{order['amount_paise'] / 100:g}) refunded by {actor}: refund {refund_id}")
        try:
            from utils_email import send_refund_email
            send_refund_email(reg.get('lead_email', ''), reg.get('lead_name', ''), event.get('title', ''),
                              order['amount_paise'] / 100, reg.get('reg_id') or row['doc_id'], refund_id)
        except Exception:
            logger.exception("Refund email failed for order %s", order['id'])
        done += 1
    if done:
        flash(f"Refunded {done} payment{'s' if done != 1 else ''}.", "success")
    if failed:
        flash(f"{failed} refund{'s' if failed != 1 else ''} failed; see the reasons below and try again.", "danger")
    if not done and not failed:
        flash("Nothing left to refund.", "info")
    return redirect(back)


@admin_bp.route('/registrations/<reg_id>/mark', methods=['POST'])
@login_required
def mark_registration(reg_id):
    """Record that a registration was refunded (money returned some other
    way) or cancelled. Either way it no longer checks in."""
    _super_only()
    action = request.form.get('action', '')
    reason = request.form.get('reason', '').strip()
    if action not in ('refunded', 'cancelled') or not reason:
        flash("Choose refunded or cancelled and give a reason.", "warning")
        return redirect('/admin/payments')
    ref = db.collection('registrations').document(reg_id)
    if not ref.get().exists:
        flash("Registration not found.", "warning")
        return redirect('/admin/payments')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    updates = {'status': 'cancelled', 'cancel_reason': reason, 'cancelled_at': now,
               'cancelled_by': session.get('user_id')}
    if action == 'refunded':
        updates.update(payment_status='Refunded', refunded_at=now)
    ref.update(updates)
    log_action(db, f"REGISTRATION_{action.upper()}", f"{reg_id} marked {action} by {session.get('user_id')}: {reason}")
    flash(f"Registration {reg_id} marked {action}.", "success")
    return redirect('/admin/payments')


@admin_bp.route('/payments/<order_id>/refund', methods=['POST'])
@login_required
def refund_order(order_id):
    """Refund a paid order that has no registration through Razorpay, once."""
    _super_only()
    from services_payments import finish_refund, start_refund, undo_refund
    if request.form.get('confirm') != 'yes':
        flash("Tick the box to confirm the refund.", "warning")
        return redirect('/admin/payments')
    order = start_refund(order_id)
    if order is None:
        flash("Nothing to refund: it was already refunded, or the payment has a registration.", "info")
        return redirect('/admin/payments')
    try:
        import routes_payment
        refund = routes_payment._rzp().payment.refund(order['payment_id'], {'amount': order['amount_paise']})
    except Exception as exc:
        undo_refund(order_id)
        flash(f"The refund failed and nothing changed: {exc}", "danger")
        return redirect('/admin/payments')
    finish_refund(order_id, str((refund or {}).get('id', '')), session.get('user_id', ''))
    log_action(db, "PAYMENT_REFUNDED",
               f"Order {order_id} (payment {order['payment_id']}, ₹{order['amount_paise'] / 100:g}) refunded by "
               f"{session.get('user_id')}: refund {(refund or {}).get('id', '')}")
    flash(f"Refunded ₹{order['amount_paise'] / 100:g} to {order['email']}.", "success")
    return redirect('/admin/payments')


# =========================================================
# 5. VIEW AUDIT LOG
# =========================================================
@admin_bp.route('/audit_log')
@login_required
@role_required(SUPER_ROLES)
def view_audit_log():
    from utils_pagination import Page, page_args, paginate_items, paginate_query
    role = (request.args.get('role') or '').strip()
    action = (request.args.get('action') or '').strip().upper()
    newest_first = db.collection('audit_log').order_by('timestamp', direction=DESCENDING)
    try:
        if page_args()[2] or role or action:
            # Filters and search run on the loaded entries; the page stays in the URL (UPG-19).
            entries = [l.to_dict() or {} for l in newest_first.stream()]
            entries = [e for e in entries
                       if (not role or str(e.get('role', '')) == role)
                       and (not action or action in str(e.get('action', '')).upper())]
            page = paginate_items(entries, search_fields=('action', 'details', 'user'))
        else:
            page = paginate_query(newest_first, transform=lambda d: d.to_dict() or {})
    except Exception:
        logger.exception("Error loading audit log")
        flash("The audit log couldn't be loaded. Try again.", "danger")
        page = Page([], 1, page_args()[1], 0)
    return render_template('admin/audit_log.html', entries=page.items, page=page,
                           role_filter=role, action_filter=action)


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
        # Email, the in-app bell, or both (UPG-75)
        channel = request.form.get('channel', 'email')
        posted = 0
        if channel in ('app', 'both'):
            from routes_notifications_v2 import create_notification
            for addr in emails:
                create_notification(db, user_email=addr, notif_type='announcement', title=subject[:200],
                                    message=message[:1000], metadata={'from': session.get('user_id')})
                posted += 1
            log_action(db, 'ANNOUNCEMENT_POSTED', f"{session.get('user_id')} → in-app {posted} | {subject}")
        if channel == 'app':
            flash(f'Posted in the app to {posted} recipient(s).', 'success')
            return render_template('admin/send_email.html', events=events,
                                   last_sent={'count': posted, 'subject': subject, 'audience': audience})
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
            flash(f'✅ Email delivered to {sent_ok} recipient(s).'
                  + (f' Also posted in the app to {posted}.' if posted else ''), 'success')

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

        # Viewing this page never migrates anything (BLK-07); use the
        # "Migrate roles" preview + confirm instead.

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
            actor_id=session.get('user_id') or '',
            actor=session,
            metadata={'source': 'admin_approval'}
        )
        flash("Event approved and published.", "success")
    except Exception as exc:
        flash(f"Approval error: {exc}", "danger")
    return _back('/admin/org_units')


@admin_bp.route('/migrate_roles', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def trigger_role_migration():
    """Preview by default; apply only with confirm=1 (BLK-07)."""
    confirm = request.form.get('confirm') == '1'
    try:
        from services_permission import migrate_roles_and_units
        result = migrate_roles_and_units(db, dry_run=not confirm)
        summary = (f"{len(result.get('migrated_admins', []))} admins → university-wide grant, "
                   f"{len(result.get('migrated_spocs', []))} SPOCs → unit grant, "
                   f"{len(result.get('backfilled_events', []))} events → 'central' unit")
        if confirm:
            flash(f"✅ Migration complete: {summary}. Migrated accounts still log in with their usual role.", "success")
        else:
            flash(f"Preview only, nothing changed: {summary}. Press \"Confirm migration\" to apply.", "info")
        if result.get('unmapped_users'):
            flash(f"⚠️ Unmapped users: {[u['email'] for u in result['unmapped_users']]}", "warning")
    except Exception as exc:
        flash(f"Migration error: {exc}", "danger")
    return redirect('/admin/org_units' if confirm else '/admin/org_units?migration_preview=1')


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



# =========================================================
# SUPER ADMIN CONTROL CENTRE (UPG-75)
# One place to see and control every event, account, registration and the
# system itself. Access was never the gap (role_required and can() let a
# Super Admin through everywhere); these pages make it usable.
# =========================================================
ASSIGNABLE_ROLES = [('Student', 'Student / participant'), ('EventCoordinator', 'Event coordinator'),
                    ('ClubSPOC', 'Club SPOC'), ('Judge', 'Judge'), ('SuperAdmin', 'Super Admin')]
SPOC_CATEGORIES = ('Technical', 'Cultural', 'Sports', 'Management', 'All')
EVENT_STATUSES = ('draft', 'pending_approval', 'published', 'registration_open', 'registration_closed',
                  'in_progress', 'evaluation', 'active', 'completed', 'certified', 'cancelled', 'archived')


def _back(default):
    """Return to the page the action came from when it's on this site."""
    from services_accounts import is_safe_next
    target = (request.form.get('next') or '').strip()
    return redirect(target if target and is_safe_next(target) else default)


def _events_index():
    """Every event with the facts the control centre lists."""
    from services_event_types import type_label
    rows = []
    for d in db.collection('events').stream():
        ev = dict(d.to_dict() or {}, id=d.id)
        ev['type_label'] = type_label(ev)
        ev['status'] = str(ev.get('status') or 'active').lower()
        ev['owner'] = (ev.get('spoc_id') or (ev.get('organizer') or {}).get('email') or ev.get('created_by_email')
                       or (ev.get('created_by') if '@' in str(ev.get('created_by') or '') else '')
                       or ev.get('coordinator_id') or '')
        rows.append(ev)
    return rows


@admin_bp.route('/events')
@login_required
@role_required(SUPER_ROLES)
def all_events():
    from utils_pagination import paginate_items
    from services_event_types import GROUPS, TYPES
    from services_workflow import WorkflowEngine
    status = (request.args.get('status') or '').strip().lower()
    kind = (request.args.get('kind') or '').strip()
    rows = _events_index()
    counts = collections.Counter(e['status'] for e in rows)
    pending = sorted([e for e in rows if e['status'] == 'pending_approval'], key=lambda e: str(e.get('date') or ''))
    if status:
        rows = [e for e in rows if e['status'] == status]
    if kind:
        rows = [e for e in rows if (e.get('event_type') or '') == kind]
    rows.sort(key=lambda e: str(e.get('created_at') or e.get('date') or ''), reverse=True)
    page = paginate_items(rows, search_fields=('title', 'venue', 'owner', 'category', 'type_label', 'id'))
    for ev in page.items:
        ev['next_states'] = WorkflowEngine.get_allowed_transitions(event_data=ev)
    spocs = sorted((d.id for d in db.collection('users').stream()
                    if _role_name(d.to_dict() or {}) in ('ClubSPOC', 'SPOC')), key=str.lower)
    return render_template('admin/events.html', page=page, events=page.items, pending=pending, counts=counts,
                           statuses=EVENT_STATUSES, status=status, kind=kind, groups=GROUPS, types=TYPES,
                           spocs=spocs, current_page='events')


@admin_bp.route('/events/<event_id>/status', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def set_event_status(event_id):
    """Move an event through its lifecycle; the workflow's own rules still apply."""
    from services_workflow import WorkflowEngine, WorkflowError
    target = (request.form.get('target_state') or '').strip().lower()
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        flash("Event not found.", "warning")
        return _back('/admin/events')
    # Whatever this event's workflow allows next, including a preset's own stages
    allowed = WorkflowEngine.get_allowed_transitions(event_data=dict(doc.to_dict() or {}, id=doc.id))
    if target not in allowed and target not in EVENT_STATUSES:
        flash("Choose a status from the list.", "warning")
        return _back('/admin/events')
    try:
        WorkflowEngine.transition_event(db, event_id=event_id, target_state=target, actor_id=session.get('user_id') or '',
                                        actor=session, metadata={'source': 'admin_control_centre'})
        log_action(db, "ADMIN_EVENT_STATUS", f"{session.get('user_id')} moved {event_id} to {target}")
        flash(f"Status changed to {target.replace('_', ' ')}.", "success")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return _back('/admin/events')


@admin_bp.route('/events/<event_id>/owner', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def set_event_owner(event_id):
    """Hand an event to another SPOC (only to a Club SPOC account)."""
    email = (request.form.get('spoc_email') or '').strip().lower()
    doc = db.collection('events').document(event_id).get()
    user = db.collection('users').document(email).get() if email else None
    if not doc.exists:
        flash("Event not found.", "warning")
        return _back('/admin/events')
    if not user or not user.exists or _role_name(user.to_dict() or {}) not in ('ClubSPOC', 'SPOC'):
        flash("Choose a Club SPOC account to hand the event to.", "danger")
        return _back('/admin/events')
    u = user.to_dict() or {}
    ev = doc.to_dict() or {}
    organizer = dict(ev.get('organizer') or {})
    previous = ev.get('spoc_id', '')
    organizer.update(name=u.get('name', email), email=email, phone=u.get('phone') or organizer.get('phone', ''))
    db.collection('events').document(event_id).update({'spoc_id': email, 'organizer': organizer})
    log_action(db, "ADMIN_EVENT_OWNER", f"{session.get('user_id')} handed {event_id} from {previous} to {email}")
    flash(f"'{ev.get('title', 'Event')}' now belongs to {u.get('name') or email}.", "success")
    return _back('/admin/events')


# ── Users ───────────────────────────────────────────────────────────────────

@admin_bp.route('/users/add', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def add_user():
    """Add an account of any role; it stays locked until its set-password link is used."""
    name = (request.form.get('name') or '').strip()[:200]
    email = (request.form.get('email') or '').strip().lower()
    role = (request.form.get('role') or '').strip()
    phone = re.sub(r'[^\d+ ]', '', request.form.get('phone') or '')[:20]
    department = (request.form.get('department') or '').strip()[:100]
    category = (request.form.get('category') or '').strip()
    problems = []
    if not name:
        problems.append("Enter the person's name.")
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        problems.append("Enter a valid email address.")
    if role not in dict(ASSIGNABLE_ROLES):
        problems.append("Choose a role.")
    if category and category not in SPOC_CATEGORIES:
        problems.append("Choose a category from the list.")
    if email and db.collection('users').document(email).get().exists:
        problems.append(f"{email} already has an account. Open it from the list to change it.")
    if problems:
        for p in problems:
            flash(p, "danger")
        return redirect('/admin/users')
    fields = {'department': department}
    if category:
        fields['category'] = category
    create_unverified_account(db, email, name, phone, role=role, **fields)
    sent = send_set_password_link(db, email, name, reason=f"by the portal administrator as {dict(ASSIGNABLE_ROLES)[role]}")
    log_action(db, "ADMIN_USER_ADDED", f"{session.get('user_id')} added {email} as {role}")
    flash(f"Account created for {email}." + (" A set-password link was emailed." if sent else
                                             " The set-password email couldn't be sent; resend it from their page."),
          "success" if sent else "warning")
    return redirect(f'/admin/users/{email}')


@admin_bp.route('/users/<path:email>', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def user_detail(email):
    """One account: details, role, active or not, their registrations and events."""
    email = email.strip().lower()
    ref = db.collection('users').document(email)
    doc = ref.get()
    if not doc.exists:
        flash("No account with that email.", "warning")
        return redirect('/admin/users')
    user = doc.to_dict() or {}
    me = (session.get('user_id') or '').lower()

    if request.method == 'POST':
        action = request.form.get('action', 'save')
        if action in ('deactivate', 'activate'):
            if email == me:
                flash("You can't deactivate your own account.", "danger")
                return redirect(f'/admin/users/{email}')
            active = action == 'activate'
            ref.update({'is_active': active})
            log_action(db, "ADMIN_USER_ACTIVE" if active else "ADMIN_USER_DEACTIVATED",
                       f"{me} {'reactivated' if active else 'deactivated'} {email}")
            flash(f"{email} {'can log in again' if active else 'is deactivated and can no longer log in'}.", "success")
            return redirect(f'/admin/users/{email}')
        role = (request.form.get('role') or '').strip()
        category = (request.form.get('category') or '').strip()
        updates = {
            'name': (request.form.get('name') or user.get('name') or '').strip()[:200],
            'phone': re.sub(r'[^\d+ ]', '', request.form.get('phone') or '')[:20],
            'department': (request.form.get('department') or '').strip()[:100],
        }
        if role and role not in dict(ASSIGNABLE_ROLES):
            flash("Choose a role from the list.", "danger")
            return redirect(f'/admin/users/{email}')
        if email == me and role and role not in ('SuperAdmin',) and _role_name(user) in SUPER_ROLE_NAMES:
            flash("You can't remove your own Super Admin role. Ask another admin.", "danger")
            return redirect(f'/admin/users/{email}')
        if role:
            updates['role'] = role
        if category in SPOC_CATEGORIES:
            updates['category'] = category
        old_role = _role_name(user)
        ref.update(updates)
        log_action(db, "ADMIN_USER_UPDATED", f"{me} updated {email}" +
                   (f" (role {old_role} → {role})" if role and role != old_role else ''))
        flash("Account saved." + (" Role changes apply at their next login." if role and role != old_role else ''),
              "success")
        return redirect(f'/admin/users/{email}')

    regs = []
    for r in db.collection('registrations').where('lead_email', '==', email).stream():
        rd = dict(r.to_dict() or {}, id=r.id)
        regs.append(rd)
    regs.sort(key=lambda r: str(r.get('registered_at') or ''), reverse=True)
    owned = sorted([dict(d.to_dict() or {}, id=d.id) for d in
                    db.collection('events').where('spoc_id', '==', email).stream()],
                   key=lambda e: str(e.get('date') or ''), reverse=True)
    return render_template('admin/user_detail.html', u=user, email=email, role=_role_name(user),
                           active=user.get('is_active', True) is not False, regs=regs, owned=owned,
                           roles=ASSIGNABLE_ROLES, categories=SPOC_CATEGORIES, is_me=email == me,
                           waiting=_waiting_for_password(user), current_page='users')


# ── Registrations ───────────────────────────────────────────────────────────

@admin_bp.route('/registrations')
@login_required
@role_required(SUPER_ROLES)
def all_registrations():
    """Find any registration across every event."""
    from utils_pagination import paginate_items
    event_filter = (request.args.get('event') or '').strip()
    status_filter = (request.args.get('status') or '').strip().lower()
    attendance_filter = (request.args.get('attendance') or '').strip().lower()
    titles = {d.id: (d.to_dict() or {}).get('title', 'Event') for d in db.collection('events').stream()}
    rows = []
    query = db.collection('registrations')
    if event_filter:
        query = query.where('event_id', '==', event_filter)
    for d in query.stream():
        r = dict(d.to_dict() or {}, id=d.id)
        r['event_title'] = titles.get(r.get('event_id'), r.get('event_title') or '—')
        r['lead_email'] = r.get('lead_email') or r.get('leadEmail') or ''
        r['lead_name'] = r.get('lead_name') or r.get('leadName') or ''
        r['team_name'] = r.get('team_name') or r.get('teamName') or ''
        if status_filter and str(r.get('status') or '').lower() != status_filter:
            continue
        if attendance_filter and str(r.get('attendance') or 'pending').lower() != attendance_filter:
            continue
        rows.append(r)
    rows.sort(key=lambda r: str(r.get('registered_at') or ''), reverse=True)
    page = paginate_items(rows, search_fields=('lead_name', 'lead_email', 'usn', 'team_name', 'id',
                                               'event_title', 'reg_id'))
    events = sorted(titles.items(), key=lambda kv: kv[1].lower())
    return render_template('admin/registrations.html', page=page, regs=page.items, events=events,
                           event_filter=event_filter, status_filter=status_filter,
                           attendance_filter=attendance_filter, current_page='registrations')


@admin_bp.route('/registrations/<reg_id>/attendance', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def set_attendance(reg_id):
    value = (request.form.get('attendance') or '').strip().capitalize()
    if value not in ('Present', 'Absent', 'Pending'):
        flash("Choose present, absent or pending.", "warning")
        return _back('/admin/registrations')
    ref = db.collection('registrations').document(reg_id)
    if not ref.get().exists:
        flash("Registration not found.", "warning")
        return _back('/admin/registrations')
    updates = {'attendance': value, 'attended': value == 'Present'}
    if value == 'Present':
        updates['checkin_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ref.update(updates)
    log_action(db, "ADMIN_ATTENDANCE", f"{session.get('user_id')} marked {reg_id} {value}")
    flash(f"Attendance set to {value.lower()}.", "success")
    return _back('/admin/registrations')


@admin_bp.route('/registrations/<reg_id>/cancel', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def cancel_registration(reg_id):
    reason = (request.form.get('reason') or '').strip()[:300]
    if not reason:
        flash("Give a reason for cancelling.", "warning")
        return _back('/admin/registrations')
    ref = db.collection('registrations').document(reg_id)
    if not ref.get().exists:
        flash("Registration not found.", "warning")
        return _back('/admin/registrations')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ref.update({'status': 'cancelled', 'cancel_reason': reason, 'cancelled_at': now,
                'cancelled_by': session.get('user_id')})
    log_action(db, "REGISTRATION_CANCELLED", f"{reg_id} cancelled by {session.get('user_id')}: {reason}")
    flash("Registration cancelled. If it was paid, refund it from Payments.", "success")
    return _back('/admin/registrations')


# ── System ──────────────────────────────────────────────────────────────────

def _configured(*names):
    import os
    return all((os.environ.get(n) or '').strip() for n in names)


def _integrations():
    """Which outside services are configured: yes/no only, never a value."""
    import os
    storage = (os.environ.get('STORAGE_TYPE') or '').strip().lower() or 'local (development only)'
    return [
        ('Email (Brevo)', _configured('BREVO_API_KEY'), 'Account emails, tickets, certificates'),
        ('Email (SMTP fallback)', _configured('MAIL_USER', 'MAIL_PASS') or _configured('MAIL_USER', 'MAIL_PASSWORD'), 'Used when Brevo is not set'),
        ('Payments (Razorpay)', _configured('RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET'), 'Paid registrations'),
        ('File storage', storage in ('s3', 'gcs'), f'Uploads and certificates: {storage}'),
        ('Google sign-in', _configured('OAUTH_GOOGLE_CLIENT_ID', 'OAUTH_GOOGLE_CLIENT_SECRET'), 'Sign in with Google'),
        ('Microsoft sign-in', _configured('OAUTH_MICROSOFT_CLIENT_ID', 'OAUTH_MICROSOFT_CLIENT_SECRET'), 'Sign in with Microsoft'),
        ('AI (Gemini)', _configured('GEMINI_API_KEY') or _configured('GOOGLE_API_KEY'), 'Event writer, matching, summaries'),
        ('WhatsApp (Twilio)', _configured('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'), 'Ticket messages'),
        ('Error monitoring (Sentry)', _configured('SENTRY_DSN'), 'Crash reports'),
        ('Scheduled jobs', _configured('CRON_SECRET'), 'Reminders, closing events, retries'),
        ('Support email', _configured('SUPPORT_EMAIL'), 'Shown to users who need help'),
    ]


def _outbox_rows():
    """Background jobs that didn't finish straight away (UPG-18)."""
    try:
        from models_pg import OutboxTask
        from services_outbox import _session
        with _session() as s:
            tasks = s.query(OutboxTask).order_by(OutboxTask.updated_at.desc()).limit(500).all()
            return [{'key': t.key, 'task': t.task_name, 'status': t.status, 'attempts': t.attempts,
                     'error': (t.last_error or '')[:300], 'updated': t.updated_at, 'next': t.next_attempt_at}
                    for t in tasks]
    except Exception as exc:
        logger.warning("Outbox read failed: %s", exc)
        return None


@admin_bp.route('/system', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def system_status():
    if request.method == 'POST' and request.form.get('action') == 'retry':
        try:
            from services_outbox import retry_due
            result = retry_due()
            log_action(db, "ADMIN_OUTBOX_RETRY", f"{session.get('user_id')} retried background jobs: {result}")
            flash(f"Retried background jobs: {result}.", "success")
        except Exception as exc:
            flash(f"Retry failed: {exc}", "danger")
        return redirect('/admin/system')
    db_ok = True
    try:
        list(db.collection('users').limit(1).stream())
    except Exception:
        db_ok = False
    jobs = _outbox_rows()
    job_counts = collections.Counter(j['status'] for j in jobs or [])
    totals = {}
    for coll in ('users', 'events', 'registrations'):
        try:
            totals[coll] = db.collection(coll).count() if hasattr(db.collection(coll), 'count') else \
                sum(1 for _ in db.collection(coll).stream())
        except Exception:
            totals[coll] = sum(1 for _ in db.collection(coll).stream())
    return render_template('admin/system.html', db_ok=db_ok, integrations=_integrations(), jobs=jobs,
                           failed=[j for j in jobs or [] if j['status'] in ('failed', 'pending')],
                           job_counts=job_counts, totals=totals, current_page='system')
