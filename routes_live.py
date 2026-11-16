"""
routes_live.py — SapthaEvent LiveOS
=====================================
Real-time event intelligence layer.

Routes (no login required):
  GET /live/<event_id>           — Full-screen projector leaderboard
  GET /live/stream/<event_id>    — SSE stream (updates every 3 s)
  GET /live/data/<event_id>      — JSON snapshot (initial load)
The board's teams and scores reach the public only once the organiser makes
the leaderboard public; the event's staff always see them (UPG-300).
"""
import json
import time

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, stream_with_context
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db
from utils import venue_label  # never an invented place (UPG-111)

live_bp = Blueprint('live', __name__, url_prefix='/live')

_ROUND_LABEL = {1: 'Round 1', 2: 'Round 2', 3: 'Semi-Final', 4: 'Final'}


def _staff_of(event_id: str) -> bool:
    """Whether the person asking is the event's staff (read once per request)."""
    import services_leaderboard
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        return False
    return services_leaderboard.is_staff(dict(doc.to_dict() or {}, id=event_id), db=db)


def _compute_leaderboard(event_id: str, staff: bool = False) -> "dict | None":
    """Read Firestore and return a ranked snapshot. Until the organiser makes
    the leaderboard public, anyone but the event's staff gets a snapshot with
    no teams and no scores (UPG-300); it is checked again on every tick, so an
    open projector shows the board once it is made public."""
    import services_leaderboard
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return None
    event = event_doc.to_dict() or {}

    cur_round = int(event.get('active_round', 1) or 1)
    public = services_leaderboard.is_public(event)
    if not public and not staff:
        return {'event_id': event_id, 'event_title': event.get('title', 'Event'), 'hidden': True,
                'message': services_leaderboard.HIDDEN_MESSAGE, 'cur_round': cur_round,
                'round_label': _ROUND_LABEL.get(cur_round, f'Round {cur_round}'),
                'board': [], 'total': 0, 'ts': int(time.time())}

    # One ranking for every board (UPG-84); unscored teams follow, unranked
    from services_leaderboard import for_event
    entries = [{'reg_id': row['id'], 'team': row['team'], 'lead': row['lead_name'], 'members': row['members'],
                'score': row['score'], 'score_text': row['score_text'], 'judges': row['judges'],
                'attended': row['attended'], 'round': row['round'], 'rank': row['rank'], 'tied': row['tied']}
               for row in for_event(db, event_id, include_unscored=True)]

    total_rounds = int(event.get('total_rounds', 1) or 1)
    return {
        'event_id':     event_id,
        'event_title':  event.get('title', 'Event'),
        'venue':        venue_label(event),   # UPG-111
        'category':     event.get('category', ''),
        'cur_round':    cur_round,
        'round_label':  _ROUND_LABEL.get(cur_round, f'Round {cur_round}'),
        'total_rounds': total_rounds,
        'status':       event.get('status', 'active'),
        'board':        entries[:25],
        'total':        len(entries),
        'ts':           int(time.time()),
        'hidden':       False,
        'staff_only':   not public,   # only the event's staff see this until it's public
    }


# ── Announcements SSE Stream ──────────────────────────────────────────────
@live_bp.route('/announcements/stream')
def announcements_stream():
    """
    Streams new announcements in real-time.
    Accepts `events` query parameter: comma-separated event IDs (e.g. ?events=id1,id2)
    """
    from flask import request
    import datetime

    # Get the comma-separated list of event IDs the user is registered for
    events_param = request.args.get('events', '')
    event_ids = [eid.strip() for eid in events_param.split(',') if eid.strip()]

    def generate():
        # Keep track of the last checked timestamp (in ISO format string)
        # Using UTC timezone aware datetime to align with post timestamp
        last_check_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Keep connection open for max 5 minutes (similar to leaderboard)
        max_ticks = 150 # 150 * 2s = 5 minutes
        for _ in range(max_ticks):
            try:
                # Query Firestore / SQL for newer announcements
                if db:
                    # Query for announcements newer than the last check time
                    query = db.collection('announcements').where('timestamp', '>', last_check_time)
                    announcements_ref = query.stream()

                    new_announcements = []
                    highest_ts = last_check_time

                    for doc in announcements_ref:
                        ad = doc.to_dict()
                        ts = ad.get('timestamp', '')
                        if ts > highest_ts:
                            highest_ts = ts

                        # Filter by client's events (if specified)
                        e_id = ad.get('event_id', '')
                        if not event_ids or e_id in event_ids:
                            new_announcements.append({
                                'id': doc.id,
                                'message': ad.get('message', ''),
                                'priority': ad.get('priority', 'info'),
                                'event_id': e_id,
                                'event_title': ad.get('event_title', 'General'),
                                'timestamp': ts
                            })

                    if new_announcements:
                        last_check_time = highest_ts
                        # Stream each new announcement to the client
                        for ann in new_announcements:
                            yield f"data: {json.dumps(ann)}\n\n"
            except Exception as e:
                yield f"data: {{\"error\":\"{str(e)[:60]}\"}}\n\n"

            time.sleep(2)

        yield "event: reconnect\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),  # type: ignore[arg-type]
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


# ── 1. Full-screen leaderboard page ──────────────────────────────────────
@live_bp.route('/<event_id>')
def leaderboard_page(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return "Event not found", 404
    event       = event_doc.to_dict() or {}
    event['id'] = event_id
    return render_template('live/leaderboard.html', event=event, event_id=event_id)


# ── 2. SSE stream ─────────────────────────────────────────────────────────
@live_bp.route('/stream/<event_id>')
def sse_stream(event_id):
    """
    Server-Sent Events endpoint. Streams a JSON leaderboard snapshot every 3 s.
    Terminates after 5 minutes so Gunicorn workers are not held indefinitely;
    the client EventSource auto-reconnects.
    """
    staff = _staff_of(event_id)

    def generate():
        max_ticks = 100          # 100 × 3 s = 5 min
        for tick in range(max_ticks):
            try:
                snapshot = _compute_leaderboard(event_id, staff=staff)
                if snapshot:
                    yield f"data: {json.dumps(snapshot)}\n\n"
                else:
                    yield "data: {\"error\":true}\n\n"
            except Exception as exc:
                yield f"data: {{\"error\":\"{str(exc)[:60]}\"}}\n\n"
            time.sleep(3)
        # Signal client to reconnect
        yield "event: reconnect\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),  # type: ignore[arg-type]
        mimetype='text/event-stream',
        headers={
            'Cache-Control':    'no-cache',
            'X-Accel-Buffering': 'no',   # disable nginx buffering
            'Connection':       'keep-alive',
        },
    )


# ── 3. JSON snapshot (for initial load before SSE connects) ──────────────
@live_bp.route('/data/<event_id>')
def live_data(event_id):
    snapshot = _compute_leaderboard(event_id, staff=_staff_of(event_id))
    if not snapshot:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(snapshot)

# ── 3b. What changes during an event, for pages that are already open (UPG-267) ──
# A page asks for the events it is showing; the answer is the registration
# state every page renders (services_registration_state), so an open page and
# a fresh one agree. Polled by static/js/live-refresh.js.
LIVE_POLL_SECONDS = 30
_LIVE_MAX_EVENTS = 60


def _asked_events():
    from flask import request
    seen = []
    for part in (request.args.get('events') or '').split(','):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen[:_LIVE_MAX_EVENTS]


def _no_store(payload):
    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@live_bp.route('/state.json')
def live_states():
    """Public: label, explanation and action of each listed event asked for.
    No names, no counts beyond what the explanation already says; an event
    that isn't publicly listed is left out, as if it didn't exist."""
    import datetime
    import services_registration_state as registration_state
    from services_event_types import is_listed
    out = {}
    for event_id in _asked_events():
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            continue
        event = doc.to_dict() or {}
        if not is_listed(event):
            continue
        out[event_id] = registration_state.public(registration_state.for_event(db, event_id, event))
    return _no_store({'events': out, 'poll': LIVE_POLL_SECONDS,
                      'at': datetime.datetime.now(registration_state.IST).strftime('%H:%M')})


@live_bp.route('/ops.json')
def live_ops():
    """Organisers: the same state plus the counts on their panels, only for
    events the signed-in person may see the numbers of."""
    import datetime
    from flask import session
    import services_entry
    import services_registration_state as registration_state
    from services_permission import can
    if 'user_id' not in session:
        return jsonify({'error': 'Sign in again to keep this page up to date.'}), 401
    out = {}
    for event_id in _asked_events():
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            continue
        event = dict(doc.to_dict() or {}, id=event_id)
        if not (can(session, 'view_analytics', event, db=db) or can(session, 'check_in', event, db=db)):
            continue
        entry = services_entry.counts(db, event_id, event)
        try:
            waiting = sum(1 for _ in db.collection('waitlists').where('event_id', '==', event_id)
                          .where('status', '==', 'waiting').stream())
        except Exception:
            waiting = 0
        view = registration_state.for_event(db, event_id, event)
        out[event_id] = dict(registration_state.public(view), status=str(event.get('status') or ''),
                             registered=entry['selected'] + entry['not_selected'],
                             checked_in=entry['checked_in'], waiting=waiting,
                             seats_limit=view['seats']['limit'], seats_free=view['seats']['free'])
    return _no_store({'events': out, 'poll': LIVE_POLL_SECONDS,
                      'at': datetime.datetime.now(registration_state.IST).strftime('%H:%M')})


# ── 4. Live Streams & Reels ──────────────────────────────────────────────
# Both pages simulate their content (viewer and like counts, bot chat, comment
# and share buttons that do nothing), so they are hidden unless
# DEMO_PAGES_ENABLED (UPG-65, D-8).
@live_bp.route('/streams')
def live_streams():
    if not current_app.config.get('DEMO_PAGES_ENABLED'):
        abort(404)
    return render_template('public/live_streams.html')

@live_bp.route('/reels')
def live_reels():
    if not current_app.config.get('DEMO_PAGES_ENABLED'):
        abort(404)
    return render_template('public/reels.html')
