from flask import Blueprint, render_template, jsonify, session
from models import db, FirebaseWrapper

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def home():
    featured_events = []
    upcoming = []
    total_events = 0
    total_regs = 0
    categories = set()
    spoc_ids = set()

    try:
        if db:
            events_ref = db.collection('events').where('status', '==', 'active').stream()
            all_events = []
            for doc in events_ref:
                data = doc.to_dict()
                all_events.append(FirebaseWrapper(doc.id, data))
                total_regs += data.get('registration_count', 0)
                cat = data.get('category', '')
                if cat:
                    categories.add(cat)
                sid = data.get('spoc_id', '')
                if sid:
                    spoc_ids.add(sid)

            all_events.sort(key=lambda x: getattr(x, 'date', '9999-99-99'))
            total_events = len(all_events)
            featured_events = [e for e in all_events if getattr(e, 'is_featured', False)][:3]
            upcoming = all_events
    except Exception as e:
        print(f"Home Page Error: {e}")

    return render_template(
        'public/home.html',
        featured_events=featured_events,
        events=upcoming,
        total_events=total_events,
        total_regs=total_regs,
        total_categories=len(categories) or 4,
        total_spocs=len(spoc_ids) or 3,
    )


@public_bp.route('/event/<event_id>')
def event_details(event_id):
    try:
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            return "Event not found", 404

        event = FirebaseWrapper(event_id, doc.to_dict())

        # Registration count for capacity bar
        reg_count = len(list(db.collection('registrations').where('event_id', '==', event_id).stream()))

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
