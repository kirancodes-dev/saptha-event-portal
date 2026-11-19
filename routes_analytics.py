# routes_analytics.py — Analytics dashboard routes
# Python 3.9 compatible

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, session
from models import db
from utils import login_required, role_required

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/analytics')
@login_required
def dashboard():
    """Retired (UPG-83): its trend figures were made up and it showed every
    event to SPOCs. Each role now has its own analytics page."""
    role = session.get('role')
    if role in ('SuperAdmin', 'Super Admin'):
        return redirect('/admin/analytics')
    if role == 'ClubSPOC':
        return redirect('/spoc/analytics')
    return redirect('/')


# ── The event summary report (UPG-273) ─────────────────────────────────────

REPORT_ROLES = ['SuperAdmin', 'Super Admin', 'UniversityAdmin', 'ClubSPOC', 'UnitAdmin', 'EventOrganizer',
                'EventCoordinator', 'Coordinator', 'IQACCoordinator', 'DepartmentAdmin']


def _summary():
    """The report over the events this person may see the figures of."""
    import services_summary
    from services_permission import can
    events = []
    for doc in db.collection('events').stream():
        event = dict(doc.to_dict() or {}, id=doc.id)
        if can(session, 'view_analytics', event, db=db):
            events.append(event)
    return services_summary.build(db, events, services_summary.read_filters(request.args))


@analytics_bp.route('/reports/events')
@login_required
@role_required(REPORT_ROLES)
def event_summary():
    """Registrations, attendance, results, feedback and certificates for each
    event in a range of dates, with what each figure counts."""
    report = _summary()
    query = request.query_string.decode('utf-8', 'ignore')
    return render_template('analytics/event_summary.html', report=report, query=query,
                           everything=session.get('role') in ('SuperAdmin', 'Super Admin', 'UniversityAdmin'))


@analytics_bp.route('/reports/events.<kind>')
@login_required
@role_required(REPORT_ROLES)
def event_summary_file(kind):
    """The same figures as a CSV file, or an Excel file with the definitions
    on a second sheet."""
    import services_export
    import services_summary
    from utils import log_action
    if kind not in ('csv', 'xlsx'):
        abort(404)
    report = _summary()
    f = report['filters']
    name = 'event-summary' + (f"-from-{f['from']}" if f['from'] else '') + (f"-to-{f['to']}" if f['to'] else '')
    if not services_export.probing():
        log_action(db, 'REPORT_EXPORTED', f"{session.get('user_id', '')}: event summary ({kind}), {report['described']} "
                                          f"{report['totals']['events']} events")
    if kind == 'csv':
        return Response(services_export.to_csv(services_summary.table(report), services_summary.COLUMNS),
                        mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={name}.csv'})
    workbook = services_export.to_xlsx([
        ('Event summary', services_summary.COLUMNS, services_summary.table(report)),
        ('What the columns count', ['Column', 'What it counts'], services_summary.definitions_table(report))])
    return Response(workbook, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename={name}.xlsx'})


@analytics_bp.route('/reports/events/definitions.csv')
@login_required
@role_required(REPORT_ROLES)
def event_summary_definitions():
    import services_export
    import services_summary
    return Response(services_export.to_csv([[h, text] for _, h, text in services_summary.DEFINITIONS],
                                           ['Column', 'What it counts']),
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=event-summary-definitions.csv'})


@analytics_bp.route('/analytics/api/stats')
@login_required
@role_required(['SuperAdmin', 'Super Admin'])   # names and payments of every registration (UPG-83)
def api_stats():
    try:
        # Get all collections streams
        events_ref = db.collection('events').stream()
        registrations_ref = db.collection('registrations').stream()
        users_ref = db.collection('users').stream()

        events = []
        for e in events_ref:
            d = e.to_dict()
            d['id'] = e.id
            events.append(d)

        registrations = []
        for r in registrations_ref:
            d = r.to_dict()
            d['id'] = r.id
            registrations.append(d)

        users = []
        for u in users_ref:
            d = u.to_dict()
            d['id'] = u.id
            users.append(d)

        total_events = len(events)
        total_registrations = len(registrations)

        # Total revenue
        total_revenue = 0.0
        for r in registrations:
            ps = str(r.get('payment_status', r.get('paymentStatus', ''))).lower()
            if 'paid' in ps:
                try:
                    fee = float(r.get('fee', 0) or 0)
                    total_revenue += fee
                except (ValueError, TypeError):
                    pass

        # Attendance Rate
        attended = sum(1 for r in registrations if r.get('attendance') == 'Present')
        attendance_rate = round((attended / total_registrations * 100), 1) if total_registrations else 0.0

        # Event category counts
        categories = {}
        for e in events:
            cat = e.get('category', 'Other')
            categories[cat] = categories.get(cat, 0) + 1

        # Event title map and registration counts
        event_titles = {}
        event_reg_counts = {}
        for e in events:
            event_titles[e['id']] = e.get('title', 'Unknown')
            event_reg_counts[e['id']] = 0

        for r in registrations:
            eid = r.get('event_id', r.get('eventId', ''))
            if eid:
                event_reg_counts[eid] = event_reg_counts.get(eid, 0) + 1

        top_events_sorted = sorted(event_reg_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_events = [{'title': event_titles.get(eid, 'Unknown'), 'count': cnt} for eid, cnt in top_events_sorted]

        # Payment Status
        payment_stats = {'paid': 0, 'unpaid': 0, 'waived': 0}
        for r in registrations:
            ps = str(r.get('payment_status', r.get('paymentStatus', 'unpaid'))).lower()
            if 'paid' in ps:
                payment_stats['paid'] += 1
            elif 'waiv' in ps:
                payment_stats['waived'] += 1
            else:
                payment_stats['unpaid'] += 1

        # Registration trend (last 30 days)
        reg_trend = {}
        for r in registrations:
            rd = r.get('registered_at', r.get('registeredAt', ''))
            if rd:
                day = str(rd)[:10]
                reg_trend[day] = reg_trend.get(day, 0) + 1

        # Sort the trend keys
        sorted_trend = {}
        for k in sorted(reg_trend.keys()):
            sorted_trend[k] = reg_trend[k]

        # Recent registrations (last 20)
        recent = []
        sorted_regs = sorted(
            registrations,
            key=lambda x: str(x.get('registered_at', x.get('registeredAt', ''))),
            reverse=True
        )[:20]

        for r in sorted_regs:
            recent.append({
                'name': r.get('lead_name', r.get('leadName', 'Unknown')),
                'event_id': r.get('event_id', r.get('eventId', '')),
                'event_title': event_titles.get(r.get('event_id', r.get('eventId', '')), 'Unknown'),
                'date': str(r.get('registered_at', r.get('registeredAt', ''))[:10]),
                'status': r.get('status', 'Unknown'),
                'payment': r.get('payment_status', r.get('paymentStatus', 'unpaid'))
            })

        return jsonify({
            'total_events': total_events,
            'total_registrations': total_registrations,
            'total_revenue': total_revenue,
            'attendance_rate': attendance_rate,
            'total_users': len(users),
            'categories': categories,
            'top_events': top_events,
            'payment_stats': payment_stats,
            'reg_trend': sorted_trend,
            'recent': recent
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Analytics error: %s", e, exc_info=True)
        return jsonify({'error': str(e)}), 500
