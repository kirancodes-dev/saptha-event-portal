"""
routes_live.py — SapthaEvent LiveOS
=====================================
Real-time event intelligence layer.

Routes (public — no auth required):
  GET /live/<event_id>           — Full-screen projector leaderboard
  GET /live/stream/<event_id>    — SSE stream (updates every 3 s)
  GET /live/data/<event_id>      — JSON snapshot (initial load)
"""
import json
import time

from flask import Blueprint, Response, jsonify, render_template, stream_with_context
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db

live_bp = Blueprint('live', __name__, url_prefix='/live')

_ROUND_LABEL = {1: 'Round 1', 2: 'Round 2', 3: 'Semi-Final', 4: 'Final'}


def _compute_leaderboard(event_id: str) -> "dict | None":
    """Read Firestore and return a ranked snapshot."""
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return None
    event = event_doc.to_dict() or {}

    cur_round = int(event.get('active_round', 1) or 1)

    regs = (db.collection('registrations')
              .where(filter=FieldFilter('event_id', '==', event_id))
              .stream())

    entries = []
    for r in regs:
        d = r.to_dict() or {}
        if d.get('is_eliminated'):
            continue
        if d.get('attendance') not in ('Present', None, ''):
            pass  # include everyone — unattended show as pending

        scores_map = d.get('scores', {})
        if scores_map:
            vals = [float(s.get('total', 0)) for s in scores_map.values()]
            avg  = round(sum(vals) / len(vals), 1)
        else:
            avg = None

        entries.append({
            'reg_id':   r.id,
            'team':     (d.get('team_name') or d.get('lead_name') or '—').strip(),
            'lead':     (d.get('lead_name') or '').strip(),
            'members':  len(d.get('members', [])),
            'score':    avg,
            'judges':   len(scores_map),
            'attended': d.get('attendance') == 'Present',
            'round':    int(d.get('current_round', 1) or 1),
        })

    # Sort: scored first (desc), unscored last
    entries.sort(key=lambda x: (x['score'] is None, -(x['score'] or 0)))
    for i, e in enumerate(entries):
        e['rank'] = i + 1

    total_rounds = int(event.get('total_rounds', 1) or 1)
    return {
        'event_id':     event_id,
        'event_title':  event.get('title', 'Event'),
        'venue':        event.get('venue', 'SNPSU Campus'),
        'category':     event.get('category', ''),
        'cur_round':    cur_round,
        'round_label':  _ROUND_LABEL.get(cur_round, f'Round {cur_round}'),
        'total_rounds': total_rounds,
        'status':       event.get('status', 'active'),
        'board':        entries[:25],
        'total':        len(entries),
        'ts':           int(time.time()),
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
    def generate():
        max_ticks = 100          # 100 × 3 s = 5 min
        for tick in range(max_ticks):
            try:
                snapshot = _compute_leaderboard(event_id)
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
    snapshot = _compute_leaderboard(event_id)
    if not snapshot:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(snapshot)

# ── 4. Live Streams & Reels ──────────────────────────────────────────────
@live_bp.route('/streams')
def live_streams():
    return render_template('public/live_streams.html')

@live_bp.route('/reels')
def live_reels():
    return render_template('public/reels.html')
