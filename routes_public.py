import os
import datetime
from flask import Blueprint, render_template, jsonify, session, send_from_directory, current_app, request
from models import FirebaseWrapper

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

public_bp = Blueprint('public', __name__)


# ─────────────────────────────────────────────────────────────
# PWA: serve manifest & service worker with correct headers
# ─────────────────────────────────────────────────────────────
@public_bp.route('/manifest.webmanifest')
def manifest():
    """Serve PWA manifest with correct content-type (required by Chrome)."""
    resp = send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'manifest.webmanifest'
    )
    resp.headers['Content-Type'] = 'application/manifest+json'
    resp.headers['Cache-Control'] = 'public, max-age=86400'  # 1 day
    return resp


@public_bp.route('/sw.js')
def service_worker():
    """Serve service worker from root scope (must be at / not /static/)."""
    resp = send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'sw.js'
    )
    resp.headers['Content-Type'] = 'application/javascript'
    # SW must not be cached — browser must always fetch the latest
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@public_bp.route('/offline')
def offline():
    """PWA offline fallback page."""
    return render_template('offline.html'), 200


@public_bp.route('/')
def home():
    featured_events = []
    upcoming = []
    total_events = 0
    total_regs = 0
    categories = set()
    spoc_ids = set()

    # Query & filter parameters
    q = (request.args.get('q') or request.args.get('search') or '').strip().lower()
    filter_dept = (request.args.get('dept') or request.args.get('department') or '').strip().lower()
    filter_type = (request.args.get('type') or request.args.get('event_type') or request.args.get('category') or '').strip().lower()
    filter_mode = (request.args.get('mode') or request.args.get('event_mode') or '').strip().lower()
    filter_fee = (request.args.get('fee') or request.args.get('pricing') or request.args.get('pricing_type') or '').strip().lower()

    # Visibility scoping
    viewer_email = (session.get('user_id') or '').strip().lower()
    viewer_role = session.get('role') or ''
    is_admin = viewer_role in ('SuperAdmin', 'Super Admin', 'UniversityAdmin')
    viewer_dept = session.get('user', {}).get('department')
    if not viewer_dept and viewer_email and db:
        try:
            udoc = db.collection('users').document(viewer_email).get()
            if udoc.exists:
                viewer_dept = udoc.to_dict().get('department')
        except Exception:
            pass

    try:
        if db:
            today = datetime.date.today().strftime('%Y-%m-%d')
            all_events = []

            # Stream events and filter
            events_ref = db.collection('events').stream()
            for doc in events_ref:
                data = doc.to_dict()
                data['id'] = doc.id
                status = (data.get('status') or 'active').strip().lower()
                if status not in ('active', 'published', 'registration_open', 'registration_closed', 'in_progress'):
                    continue

                # Visibility guard: department-only events
                ev_visibility = (data.get('visibility') or 'Public').strip().lower()
                ev_dept = str(data.get('org_unit_id') or data.get('department') or '').strip().lower()
                if ev_visibility in ('department', 'department_only') or data.get('department_only') is True:
                    if not is_admin:
                        if not viewer_email or not viewer_dept or viewer_dept.lower() != ev_dept:
                            continue

                # Search query filter (title, description, venue, category, rules)
                if q:
                    searchable = f"{data.get('title','')} {data.get('description','')} {data.get('venue','')} {data.get('category','')} {data.get('rules','')}".lower()
                    if q not in searchable:
                        continue

                # Department filter
                if filter_dept and filter_dept != 'all':
                    if filter_dept not in (ev_dept, str(data.get('org_unit_id') or '').lower(), str(data.get('department') or '').lower()):
                        continue

                # Event type filter
                if filter_type and filter_type != 'all':
                    ev_type_val = str(data.get('event_type') or data.get('category') or '').lower()
                    if filter_type not in ev_type_val:
                        continue

                # Mode filter
                if filter_mode and filter_mode != 'all':
                    ev_mode_val = str(data.get('mode') or data.get('event_mode') or ('online' if 'online' in str(data.get('venue') or '').lower() else 'offline')).lower()
                    if filter_mode != ev_mode_val:
                        continue

                # Fee filter
                if filter_fee and filter_fee != 'all':
                    fee_val = float(data.get('fee') or (data.get('fees') or {}).get('regular', 0) or 0)
                    is_free = (fee_val == 0.0) or (data.get('pricing_type') == 'free')
                    if filter_fee == 'free' and not is_free:
                        continue
                    if filter_fee == 'paid' and is_free:
                        continue

                all_events.append(FirebaseWrapper(doc.id, data))
                total_regs += data.get('registration_count', 0)
                cat = data.get('category', '')
                if cat:
                    categories.add(cat)
                sid = data.get('spoc_id', '')
                if sid:
                    spoc_ids.add(sid)

            # Sort by date
            all_events.sort(key=lambda x: str(getattr(x, 'date', '9999-12-31')))
            total_events = len(all_events)
            featured_events = [e for e in all_events if getattr(e, 'is_featured', False)][:3]
            upcoming = all_events
    except Exception as e:
        current_app.logger.error(f"Home Page Error: {e}")

    if request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'total_events': total_events,
            'events': [e._data for e in upcoming] if upcoming else [],
        })

    return render_template(
        'public/home.html',
        featured_events=featured_events,
        events=upcoming,
        total_events=total_events,
        total_regs=total_regs,
        total_categories=len(categories) or 4,
        total_spocs=len(spoc_ids) or 3,
        search_query=q,
    )


@public_bp.route('/event/<event_id>')
def event_details(event_id):
    try:
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            return "Event not found", 404

        raw_event = doc.to_dict() or {}
        raw_event['id'] = event_id
        status = (raw_event.get('status') or '').lower()
        if status in ('draft', 'pending_approval'):
            from services_permission import can
            if not can(session, 'edit_event', raw_event, db=db):
                return "Event not found", 404

        event = FirebaseWrapper(event_id, raw_event)

        # Registration count for capacity bar (use efficient count instead of streaming all docs)
        try:
            # Try to use aggregation for efficient count (Firebase feature)
            reg_count = db.collection('registrations').where('event_id', '==', event_id).count().get().total
        except:
            # Fallback: count with limit to prevent freezing with large datasets
            registrations_list = list(
                db.collection('registrations')
                  .where('event_id', '==', event_id)
                  .limit(10000)  # Safety limit
                  .stream()
            )
            reg_count = len(registrations_list)

        is_registered = False
        if session.get('user_id'):
            existing = list(
                db.collection('registrations')
                  .where('event_id', '==', event_id)
                  .where('lead_email', '==', session['user_id'])
                  .limit(1).stream()
            )
            is_registered = bool(existing)

        # Pre-fill form for logged-in students
        prefill = None
        if session.get('role') == 'Student':
            user_doc = db.collection('users').document(session['user_id']).get()
            if user_doc.exists:
                u = user_doc.to_dict()
                prefill = {
                    'name':  u.get('name', ''),
                    'email': session['user_id'],
                    'usn':   u.get('usn', ''),
                    'phone': u.get('phone', ''),
                }

        return render_template(
            'public/event_details.html',
            event=event,
            is_registered=is_registered,
            reg_count=reg_count,
            prefill=prefill,
        )
    except Exception as e:
        print(f"Event Details Error: {e}")
        return "System Error", 500


@public_bp.route('/api/events')
def get_events_json():
    """FullCalendar JSON feed."""
    try:
        if not db:
            return jsonify([])
        cat_colors = {
            'Technical':  '#1a2557',
            'Cultural':   '#7c3aed',
            'Sports':     '#16a34a',
            'Management': '#d97706',
            'Workshop':   '#0891b2',
        }
        events_list = []
        for doc in db.collection('events').where('status', '==', 'active').stream():
            data = doc.to_dict()
            cat  = data.get('category', '')
            events_list.append({
                'title':     data.get('title'),
                'start':     data.get('date'),
                'url':       f"/event/{doc.id}",
                'color':     cat_colors.get(cat, '#c9a45e'),
                'className': 'fc-event-custom',
            })
        return jsonify(events_list)
    except Exception:
        return jsonify([])

@public_bp.route('/platform/wayfinder')
def wayfinder():
    return render_template('public/wayfinder.html')
