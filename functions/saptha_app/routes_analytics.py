# routes_analytics.py — Analytics dashboard routes
# Python 3.9 compatible

import datetime
from flask import Blueprint, render_template, jsonify, session, redirect
from models import db
from utils import login_required, role_required

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/analytics')
@login_required
@role_required(['SuperAdmin', 'Super Admin', 'ClubSPOC', 'Coordinator'])
def dashboard():
    return render_template('analytics/dashboard.html')


@analytics_bp.route('/analytics/api/stats')
@login_required
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
