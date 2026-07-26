"""
routes_judge.py  —  Judge Panel
================================
Fixes in this version
  - All .where() → filter=FieldFilter()   (no more UserWarning)
  - Open Hall Mode: when event.open_hall_mode is True, judge sees ALL
    present teams regardless of assigned_judge_email
  - Score key uses email as-is (dict key), not a sanitised version
  - /judge/leaderboard/<event_id>  — live JSON feed for AJAX refresh
  - /judge/score_inline/<reg_id>   — AJAX endpoint (returns JSON)
    so judge can score without page reload
"""
import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db
from utils import login_required, role_required, log_action, safe_int

judge_bp    = Blueprint('judge', __name__, url_prefix='/judge')
JUDGE_ROLES = ['Judge', 'SuperAdmin', 'Super Admin']


def _ff(f, op, v):
    return FieldFilter(f, op, v)


# =========================================================
# 1. JUDGE DASHBOARD
# =========================================================
@judge_bp.route('/dashboard')
@login_required
@role_required(JUDGE_ROLES)
def dashboard():
    email     = session.get('user_id')
    user_role = session.get('role')
    my_events = []

    for e in (db.collection('events')
                .where(filter=_ff('status', '==', 'active'))
                .stream()):
        data  = e.to_dict()
        staff = data.get('staff', [])
        assigned = any(
            s.get('email') == email and s.get('role') == 'Judge'
            for s in staff
        )
        if assigned or user_role in ('SuperAdmin', 'Super Admin'):
            data['id'] = e.id

            # Count scored / total teams for progress bar
            regs       = list(db.collection('registrations')
                               .where(filter=_ff('event_id', '==', e.id))
                               .stream())
            present    = [r for r in regs if r.to_dict().get('attendance') == 'Present'
                          and not r.to_dict().get('is_eliminated')]
            scored_by_me = sum(1 for r in present if email in r.to_dict().get('scores', {}))
            data['teams_total']    = len(present)
            data['teams_scored']   = scored_by_me
            data['open_hall_mode'] = data.get('open_hall_mode', False)
            my_events.append(data)

    return render_template('judge/dashboard.html',
                            events=my_events,
                            user_name=session.get('name'))


# =========================================================
# 2. TEAMS LIST FOR SCORING
# =========================================================
@judge_bp.route('/event/<event_id>')
@login_required
@role_required(JUDGE_ROLES)
def event_teams(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/judge/dashboard')

    event       = event_doc.to_dict()
    event['id'] = event_id
    judge_email = session.get('user_id')
    open_hall   = event.get('open_hall_mode', False)
    cur_round   = event.get('active_round', 1)

    # Base query — present, not eliminated, current round
    all_regs = (db.collection('registrations')
                  .where(filter=_ff('event_id',    '==', event_id))
                  .where(filter=_ff('attendance',  '==', 'Present'))
                  .stream())

    teams = []
    for r in all_regs:
        d = r.to_dict()
        if d.get('is_eliminated'):
            continue
        if d.get('current_round', 1) != cur_round:
            continue
        # In normal mode, only show teams assigned to this judge
        if not open_hall and d.get('assigned_judge_email') != judge_email:
            continue

        d['id']       = r.id
        d['my_score'] = d.get('scores', {}).get(judge_email)
        teams.append(d)

    teams.sort(key=lambda x: x.get('team_name', ''))
    return render_template('judge/teams.html',
                            event=event, teams=teams,
                            judge_email=judge_email,
                            open_hall=open_hall)


# =========================================================
# 3. SUBMIT SCORE (form POST — full page)
# =========================================================
@judge_bp.route('/submit_score/<reg_id>', methods=['POST'])
@login_required
@role_required(JUDGE_ROLES)
def submit_score(reg_id):
    try:
        reg_ref  = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()
        if not reg_data:
            flash("Registration not found.", "danger")
            return redirect('/judge/dashboard')

        event_id  = reg_data.get('event_id')
        event_doc = db.collection('events').document(event_id).get().to_dict()
        if event_doc.get('scoring_locked'):
            flash("Scoring is locked by the SPOC for this round.", "danger")
            return redirect(f'/judge/event/{event_id}')
        criteria  = event_doc.get('judging_criteria', ['Overall Score'])

        score_details = {}
        total_score   = 0
        for c in criteria:
            key = f"score_{c.replace(' ', '_').lower()}"
            val = safe_int(request.form.get(key, 0))
            score_details[c] = val
            total_score      += val

        avg_score   = round(total_score / len(criteria), 1)
        judge_email = session.get('user_id')
        remarks     = request.form.get('remarks', '').strip()

        reg_ref.set({
            'scores': {
                judge_email: {
                    'details':      score_details,
                    'total':        avg_score,
                    'raw_total':    total_score,
                    'remarks':      remarks,
                    'judge_name':   session.get('name'),
                    'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            }
        }, merge=True)

        log_action(db, "SCORE_SUBMITTED",
                   f"Judge {judge_email} scored {reg_id} — avg {avg_score}")
        flash(f"Score saved! Average: {avg_score}", "success")
        return redirect(f'/judge/event/{event_id}')

    except Exception as exc:
        flash(f"Error submitting score: {exc}", "danger")
        return redirect('/judge/dashboard')


# =========================================================
# 4. SCORE VIA AJAX (returns JSON — used by scoring modal)
# =========================================================
@judge_bp.route('/score_inline/<reg_id>', methods=['POST'])
@login_required
@role_required(JUDGE_ROLES)
def score_inline(reg_id):
    """AJAX endpoint: POST JSON → returns JSON. No page reload."""
    try:
        body      = request.get_json() or {}
        scores    = body.get('scores', {})      # {criterion: value}
        remarks   = body.get('remarks', '')

        reg_ref  = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()
        if not reg_data:
            return jsonify({'status': 'error', 'message': 'Registration not found'}), 404

        event_doc = db.collection('events').document(reg_data['event_id']).get().to_dict()
        if event_doc.get('scoring_locked'):
            return jsonify({'status': 'locked',
                            'message': 'Scoring is locked by the SPOC for this round.'}), 403
        criteria  = event_doc.get('judging_criteria', ['Overall Score'])

        total = sum(safe_int(scores.get(c, 0)) for c in criteria)
        avg   = round(total / len(criteria), 1)

        judge_email = session.get('user_id')
        reg_ref.set({
            'scores': {
                judge_email: {
                    'details':      scores,
                    'total':        avg,
                    'raw_total':    total,
                    'remarks':      remarks,
                    'judge_name':   session.get('name'),
                    'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            }
        }, merge=True)

        log_action(db, "SCORE_INLINE",
                   f"Judge {judge_email} scored {reg_id} (AJAX) — avg {avg}")
        return jsonify({'status': 'ok', 'avg': avg, 'message': f'Score saved — avg {avg}'})

    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


# =========================================================
# 5. LIVE LEADERBOARD JSON (AJAX polling — 10s refresh)
# =========================================================
@judge_bp.route('/leaderboard/<event_id>')
@login_required
@role_required(JUDGE_ROLES)
def leaderboard(event_id):
    """Returns JSON leaderboard for AJAX refresh on teams page."""
    regs = (db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream())

    board = []
    for r in regs:
        d = r.to_dict()
        if d.get('is_eliminated'):
            continue
        scores = d.get('scores', {})
        if not scores:
            continue
        avg = round(
            sum(safe_int(s.get('total', 0)) for s in scores.values()) / len(scores), 1
        )
        board.append({
            'team_name': d.get('team_name', '—'),
            'lead_name': d.get('lead_name', ''),
            'score':     avg,
            'judges':    len(scores),
            'room':      d.get('assigned_room', '—'),
        })

    board.sort(key=lambda x: x['score'], reverse=True)
    for i, row in enumerate(board):
        row['rank'] = i + 1

    return jsonify({'status': 'ok', 'data': board})


# =========================================================
# AI SPEECH-TO-SCORE DICTATION PARSER
# =========================================================
@judge_bp.route('/speech-to-score', methods=['POST'])
@login_required
@role_required(JUDGE_ROLES)
def speech_to_score():
    try:
        body       = request.get_json() or {}
        transcript = body.get('transcript', '').strip()
        criteria   = body.get('criteria', ['Overall Score'])

        if not transcript:
            return jsonify({'status': 'error', 'message': 'No speech transcript received.'}), 400

        api_key = current_app.config.get('GEMINI_API_KEY', '')
        result  = None

        if api_key:
            try:
                from google import genai
                import json
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"You are a speech-to-score parser for an event judging panel. Extract scores (out of 100) and remarks from this transcript: '{transcript}'.\n"
                    f"The target criteria are: {criteria}.\n"
                    f"Return ONLY a JSON object with this exact structure (no markdown fences, no prose):\n"
                    f"{{\n"
                    f"  \"scores\": {{\n"
                    + ",\n".join([f"    \"{c}\": <int>" for c in criteria])
                    + f"\n  }},\n"
                    f"  \"remarks\": \"<string: extracted remarks/comments>\"\n"
                    f"}}\n"
                )
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                raw = response.text.strip()
                if raw.startswith('```'):
                    raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
                    raw = raw.rsplit('```', 1)[0].strip()
                result = json.loads(raw)
            except Exception as e:
                current_app.logger.error("Error in speech-to-score Gemini parser: %s", e)

        if not result:
            # Fallback regex-based parsing
            import re
            scores  = {}
            remarks = ""
            words   = transcript.lower()
            for c in criteria:
                pattern = rf"\b{re.escape(c.lower())}\b.*?(\d+)"
                match   = re.search(pattern, words)
                if not match:
                    pattern = rf"(\d+)\s*(?:points|score)?\s*(?:for|on|in|to)?\s*\b{re.escape(c.lower())}\b"
                    match   = re.search(pattern, words)
                if match:
                    val = int(match.group(1))
                    if 0 <= val <= 100:
                        scores[c] = val
            remarks_match = re.search(r"(?:remarks|comments|comment|remark)\b\s*(?:is|are|was)?\s*(.*)", words, re.IGNORECASE)
            if remarks_match:
                remarks = remarks_match.group(1).strip()
            else:
                if not scores:
                    remarks = transcript
            result = {'scores': scores, 'remarks': remarks}

        return jsonify({'status': 'ok', 'result': result})

    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500

