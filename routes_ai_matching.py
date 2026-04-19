"""
routes_ai_matching.py  —  AI Judge–Team Matching
=================================================
Uses Gemini 2.5 Flash to intelligently match judges to teams
based on project domain vs judge area of expertise.

Replaces the random shuffle in allocate_rooms with a semantic
matching pass: Gemini reads every team's project title + abstract
and every judge's expertise, then returns an optimal assignment
matrix with per-match confidence scores and reasoning.

Flow
----
1. POST /ai/match_judges/<event_id>
   - Reads all judges (from event.staff) and their expertise
     (from users collection, falls back to expertise in form)
   - Reads all registrations and their project_title / project_desc
     (from form_answers or top-level fields)
   - Builds a structured prompt → Gemini → parses JSON response
   - Saves the proposed match plan to events/<id>/ai_match_plan
   - Returns JSON {status, matches, unmatched, reasoning}

2. GET  /ai/match_status/<event_id>
   - Returns the saved plan so the UI can display it without re-calling Gemini

3. POST /ai/apply_match/<event_id>
   - Takes the confirmed plan from request body
   - Writes assigned_judge_email + assigned_judge_name + assigned_room
     to each registration
   - Marks events/<id>.ai_match_applied = True

4. POST /ai/update_expertise/<event_id>
   - AJAX endpoint: saves a judge's expertise string to their user doc
   - Called before running the match so expertise is always fresh

Firestore writes
----------------
  events/<id>:
    ai_match_plan      {matches, reasoning, generated_at}
    ai_match_applied   True/False

  registrations/<reg_id>:
    assigned_judge_email
    assigned_judge_name
    assigned_room        (same as judge's name — 1 judge = 1 room model)

  users/<email>:
    expertise            free-text, e.g. "Machine Learning, Computer Vision"
"""

import datetime
import json
import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session
from google import genai
from google.cloud.firestore_v1.base_query import FieldFilter

from models import db
from utils import login_required, role_required, log_action, safe_int

logger   = logging.getLogger(__name__)
ai_bp    = Blueprint('ai', __name__, url_prefix='/ai')

COORD_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin']


# ── helpers ──────────────────────────────────────────────

def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _gemini_client():
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY not configured.')
    return genai.Client(api_key=api_key)


def _project_info(reg: dict) -> dict:
    """Extract project title and description from a registration dict."""
    answers = reg.get('form_answers', {})

    # Try common field names used in form builder
    title = (
        reg.get('project_title') or
        answers.get('project_title') or answers.get('Project Title') or
        answers.get('title') or answers.get('project_name') or
        answers.get('Project Name') or
        reg.get('team_name', 'Unnamed Project')
    )
    desc = (
        reg.get('project_desc') or reg.get('abstract') or
        answers.get('project_desc') or answers.get('Project Description') or
        answers.get('abstract') or answers.get('Abstract') or
        answers.get('problem_statement') or answers.get('Problem Statement') or
        answers.get('description') or answers.get('Description') or
        ''
    )
    domain = (
        answers.get('domain') or answers.get('Domain') or
        answers.get('track') or answers.get('Track') or
        answers.get('category') or ''
    )
    return {'title': str(title)[:120], 'desc': str(desc)[:300], 'domain': str(domain)[:60]}


# =========================================================
# 1. RUN AI MATCHING
# =========================================================
@ai_bp.route('/match_judges/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def match_judges(event_id):
    """
    POST /ai/match_judges/<event_id>
    Runs Gemini matching and saves the plan. Returns JSON.
    """
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404

        event_data = event_doc.to_dict()
        event_title = event_data.get('title', 'Event')

        # ── 1. Collect judges + their expertise ──────────────
        raw_judges = [s for s in event_data.get('staff', []) if s.get('role') == 'Judge']
        if not raw_judges:
            return jsonify({'status': 'error', 'message': 'No judges assigned to this event yet. Add judges first via the Assign Staff panel.'}), 400

        judges = []
        for j in raw_judges:
            user_doc = db.collection('users').document(j['email']).get()
            expertise = ''
            if user_doc.exists:
                expertise = user_doc.to_dict().get('expertise', '')
            judges.append({
                'email':     j['email'],
                'name':      j['name'],
                'expertise': expertise or 'General evaluation',
            })

        # ── 2. Collect registrations + project info ───────────
        regs_raw = list(
            db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream()
        )
        regs = []
        for r in regs_raw:
            d = r.to_dict()
            if d.get('is_eliminated'):
                continue
            proj = _project_info(d)
            regs.append({
                'reg_id':    r.id,
                'team_name': d.get('team_name', r.id),
                'title':     proj['title'],
                'desc':      proj['desc'],
                'domain':    proj['domain'],
            })

        if not regs:
            return jsonify({'status': 'error', 'message': 'No confirmed registrations yet.'}), 400

        # ── 3. Build Gemini prompt ────────────────────────────
        judges_block = '\n'.join(
            f'  J{i+1}. {j["name"]} <{j["email"]}> — expertise: {j["expertise"]}'
            for i, j in enumerate(judges)
        )
        teams_block = '\n'.join(
            f'  T{i+1}. Team: {r["team_name"]} | Title: {r["title"]} | Domain: {r["domain"]} | Abstract: {r["desc"]}'
            for i, r in enumerate(regs)
        )

        prompt = f"""You are an expert academic event coordinator for {event_title} at Sapthagiri NPS University.

Your task: assign each judge to a group of teams, matching judge expertise to team project domains as closely as possible. Each judge must be assigned AT LEAST one team. Distribute teams as evenly as possible.

JUDGES ({len(judges)} total):
{judges_block}

TEAMS ({len(regs)} total):
{teams_block}

Rules:
- Every team must be assigned to exactly one judge.
- Distribute teams evenly (aim for {len(regs) // max(len(judges),1)}–{(len(regs) // max(len(judges),1)) + 2} teams per judge).
- Prefer domain/expertise match over even distribution if a strong match exists.
- If a judge's expertise is "General evaluation", assign them teams where no other judge is a better fit.

Return ONLY valid JSON in this exact schema — no prose, no markdown fences:
{{
  "matches": [
    {{
      "judge_email": "<email>",
      "judge_name": "<name>",
      "assigned_teams": [
        {{
          "reg_id": "<reg_id>",
          "team_name": "<name>",
          "match_reason": "<one sentence why this judge fits this team>",
          "confidence": <integer 60-100>
        }}
      ]
    }}
  ],
  "overall_reasoning": "<2-3 sentence summary of the matching strategy used>",
  "avg_confidence": <integer>
}}"""

        # ── 4. Call Gemini ────────────────────────────────────
        client   = _gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip()

        # Strip markdown fences if present
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            raw = raw.rsplit('```', 1)[0].strip()

        plan = json.loads(raw)

        # ── 5. Validate all reg_ids are present ───────────────
        assigned_reg_ids = {
            t['reg_id']
            for m in plan.get('matches', [])
            for t in m.get('assigned_teams', [])
        }
        known_ids = {r['reg_id'] for r in regs}
        unmatched = list(known_ids - assigned_reg_ids)

        # Auto-assign any unmatched to the judge with fewest teams
        if unmatched:
            match_list = plan['matches']
            for rid in unmatched:
                team = next((r for r in regs if r['reg_id'] == rid), None)
                if not team:
                    continue
                # Find judge with fewest assigned teams
                lightest = min(match_list, key=lambda m: len(m['assigned_teams']))
                lightest['assigned_teams'].append({
                    'reg_id':       rid,
                    'team_name':    team['team_name'],
                    'match_reason': 'Auto-assigned (fallback)',
                    'confidence':   60,
                })

        plan['generated_at']  = datetime.datetime.utcnow().isoformat()
        plan['event_id']      = event_id
        plan['unmatched_count'] = len(unmatched)

        # ── 6. Save plan to Firestore ─────────────────────────
        db.collection('events').document(event_id).update({
            'ai_match_plan':    plan,
            'ai_match_applied': False,
        })

        log_action(db, 'AI_MATCH_GENERATED',
                   f'AI match plan for {event_id}: {len(regs)} teams → {len(judges)} judges')

        return jsonify({'status': 'ok', 'plan': plan})

    except json.JSONDecodeError as exc:
        logger.error('Gemini returned non-JSON: %s', exc)
        return jsonify({'status': 'error', 'message': 'AI returned an unreadable response. Please try again.'}), 500
    except Exception as exc:
        logger.error('AI matching error: %s', exc)
        return jsonify({'status': 'error', 'message': str(exc)}), 500


# =========================================================
# 2. GET SAVED MATCH PLAN
# =========================================================
@ai_bp.route('/match_status/<event_id>')
@login_required
@role_required(COORD_ROLES)
def match_status(event_id):
    """GET /ai/match_status/<event_id> — returns saved plan JSON."""
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'status': 'error', 'message': 'Event not found'}), 404

    data = event_doc.to_dict()
    plan = data.get('ai_match_plan')
    if not plan:
        return jsonify({'status': 'none'})

    return jsonify({
        'status':   'ok',
        'plan':     plan,
        'applied':  data.get('ai_match_applied', False),
    })


# =========================================================
# 3. APPLY MATCH PLAN TO FIRESTORE
# =========================================================
@ai_bp.route('/apply_match/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def apply_match(event_id):
    """
    POST /ai/apply_match/<event_id>
    Body: {matches: [...]}  (same structure as plan.matches)
    Writes assigned_judge_email, assigned_judge_name, assigned_room
    to each registration.
    """
    try:
        body    = request.get_json() or {}
        matches = body.get('matches', [])
        if not matches:
            # Fall back to saved plan
            event_doc = db.collection('events').document(event_id).get()
            matches   = event_doc.to_dict().get('ai_match_plan', {}).get('matches', [])

        applied = 0
        for match in matches:
            judge_email = match['judge_email']
            judge_name  = match['judge_name']
            # Use judge name as room label (clean, readable on tickets)
            room_label  = f"Judge: {judge_name}"

            for team in match.get('assigned_teams', []):
                reg_id = team.get('reg_id')
                if not reg_id:
                    continue
                db.collection('registrations').document(reg_id).update({
                    'assigned_judge_email': judge_email,
                    'assigned_judge_name':  judge_name,
                    'assigned_room':        room_label,
                })
                applied += 1

        db.collection('events').document(event_id).update({
            'ai_match_applied':    True,
            'ai_match_applied_at': datetime.datetime.utcnow().isoformat(),
        })
        log_action(db, 'AI_MATCH_APPLIED',
                   f'Applied AI match for event {event_id}: {applied} assignments')

        return jsonify({'status': 'ok', 'applied': applied,
                        'message': f'{applied} teams assigned to judges successfully.'})

    except Exception as exc:
        logger.error('Apply match error: %s', exc)
        return jsonify({'status': 'error', 'message': str(exc)}), 500


# =========================================================
# 4. UPDATE JUDGE EXPERTISE (AJAX)
# =========================================================
@ai_bp.route('/update_expertise', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def update_expertise():
    """
    POST /ai/update_expertise
    Body: {email: str, expertise: str}
    Saves expertise to the judge's user doc.
    """
    body      = request.get_json() or {}
    email     = body.get('email', '').strip().lower()
    expertise = body.get('expertise', '').strip()

    if not email:
        return jsonify({'status': 'error', 'message': 'Email required'}), 400

    db.collection('users').document(email).set(
        {'expertise': expertise}, merge=True
    )
    return jsonify({'status': 'ok', 'message': f'Expertise saved for {email}'})


# =========================================================
# 5. AI MATCHING PAGE (HTML)
# =========================================================
@ai_bp.route('/match_page/<event_id>')
@login_required
@role_required(COORD_ROLES)
def match_page(event_id):
    """GET /ai/match_page/<event_id> — full matching UI page."""
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/coordinator/dashboard')

    event_data       = event_doc.to_dict()
    event_data['id'] = event_id

    # Collect judges with their saved expertise
    raw_judges = [s for s in event_data.get('staff', []) if s.get('role') == 'Judge']
    judges = []
    for j in raw_judges:
        ud = db.collection('users').document(j['email']).get()
        expertise = ud.to_dict().get('expertise', '') if ud.exists else ''
        judges.append({
            'email':     j['email'],
            'name':      j['name'],
            'expertise': expertise,
        })

    # Collect registrations with project info
    regs_raw = list(
        db.collection('registrations')
          .where(filter=_ff('event_id', '==', event_id))
          .stream()
    )
    teams = []
    for r in regs_raw:
        d = r.to_dict()
        if d.get('is_eliminated'):
            continue
        proj = _project_info(d)
        teams.append({
            'reg_id':     r.id,
            'team_name':  d.get('team_name', r.id),
            'lead_name':  d.get('lead_name', ''),
            'title':      proj['title'],
            'desc':       proj['desc'],
            'domain':     proj['domain'],
            'assigned_judge_email': d.get('assigned_judge_email', ''),
            'assigned_judge_name':  d.get('assigned_judge_name', ''),
        })

    saved_plan = event_data.get('ai_match_plan')
    applied    = event_data.get('ai_match_applied', False)

    return render_template(
        'coordinator/ai_matching.html',
        event      = event_data,
        judges     = judges,
        teams      = teams,
        saved_plan = saved_plan,
        applied    = applied,
        user_name  = session.get('name'),
    )


# =========================================================
# ─── AI RESULT SUMMARIES ────────────────────────────────
# =========================================================

def _build_score_block(reg_data: dict, criteria: list) -> dict:
    """
    Given a registration dict and the event's judging_criteria list,
    returns a tidy dict ready for the Gemini prompt and for storage.
    """
    scores      = reg_data.get('scores', {})      # {judge_email: {details, total, remarks}}
    per_judge   = []
    all_totals  = []
    all_remarks = []

    for judge_email, entry in scores.items():
        if not isinstance(entry, dict):
            continue
        total   = float(entry.get('total', 0))
        details = entry.get('details', {})   # {criterion: value}
        remarks = (entry.get('remarks') or '').strip()
        per_judge.append({
            'judge':   entry.get('judge_name', judge_email),
            'total':   total,
            'details': details,
            'remarks': remarks,
        })
        all_totals.append(total)
        if remarks:
            all_remarks.append(remarks)

    avg_total = round(sum(all_totals) / len(all_totals), 2) if all_totals else 0.0

    # Per-criterion averages across all judges
    crit_avgs = {}
    for c in criteria:
        vals = [pj['details'].get(c, 0) for pj in per_judge if c in pj['details']]
        crit_avgs[c] = round(sum(vals) / len(vals), 1) if vals else 0.0

    return {
        'avg_total':  avg_total,
        'crit_avgs':  crit_avgs,
        'remarks':    all_remarks,
        'judge_count': len(per_judge),
    }


def _build_summary_prompt(event_title: str, criteria: list,
                           teams_data: list, event_category: str) -> str:
    """
    Builds the batch prompt sent to Gemini for all teams.
    teams_data: list of dicts with reg_id, team_name, lead_name,
                score_block, rank, project_title, project_domain
    """
    teams_block = ''
    for t in teams_data:
        sb = t['score_block']
        crit_lines = '\n'.join(
            f'      {c}: {sb["crit_avgs"].get(c, "N/A")}/100'
            for c in criteria
        )
        remarks_text = ' | '.join(sb['remarks']) if sb['remarks'] else 'No remarks provided.'
        teams_block += f"""
  [{t['reg_id']}]
  Team: {t['team_name']}  |  Lead: {t['lead_name']}  |  Rank: #{t['rank']}
  Project: {t.get('project_title', t['team_name'])}  |  Domain: {t.get('project_domain', 'General')}
  Average Score: {sb['avg_total']}/100  |  Judges: {sb['judge_count']}
  Per-criterion averages:
{crit_lines}
  Judge remarks: {remarks_text}
"""

    return f"""You are the official result summariser for {event_title} ({event_category}) at Sapthagiri NPS University.

For each team below, write a structured performance summary that will be shown:
  1. To the SPOC/Coordinator as a full review
  2. To the student on their personal dashboard (encouraging, constructive)

Teams and their scores:
{teams_block}

For EVERY team, write a JSON object with this exact schema:
{{
  "reg_id": "<from above>",
  "headline": "<one punchy sentence ≤12 words — e.g. 'Strong technical depth, presentation needs polish'>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3 if warranted>"],
  "improvements": ["<area 1>", "<area 2>"],
  "narrative": "<3–4 sentences: what the team did well, where they can grow, encouragement. Warm professional tone. Reference actual criterion scores if they are notably high or low.>",
  "student_message": "<1–2 sentences shown only to the student. Warm, personal, forward-looking. Never mention exact scores here.>"
}}

Return a JSON array of these objects — one per team, in the same order as listed above.
Return ONLY valid JSON. No prose, no markdown fences, no preamble.
"""


@ai_bp.route('/generate_summaries/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def generate_summaries(event_id):
    """
    POST /ai/generate_summaries/<event_id>
    Batch-generates AI summaries for all scored teams.
    Saves each summary to registrations/<reg_id>.ai_summary
    and a summary index to events/<event_id>.ai_summaries_generated.
    Returns JSON {status, count, summaries[]}.
    """
    try:
        event_doc  = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404

        event_data = event_doc.to_dict()
        criteria   = event_data.get('judging_criteria', ['Overall Score'])
        event_title    = event_data.get('title', 'Event')
        event_category = event_data.get('category', 'General')

        # ── 1. Collect all scored registrations + build leaderboard ──
        regs_raw = list(
            db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream()
        )
        scored = []
        for r in regs_raw:
            d = r.to_dict()
            if d.get('is_eliminated'):
                continue
            if not d.get('scores'):
                continue
            sb = _build_score_block(d, criteria)
            proj = _project_info(d)
            scored.append({
                'reg_id':         r.id,
                'team_name':      d.get('team_name', r.id),
                'lead_name':      d.get('lead_name', ''),
                'lead_email':     d.get('lead_email', ''),
                'score_block':    sb,
                'project_title':  proj['title'],
                'project_domain': proj['domain'],
            })

        if not scored:
            return jsonify({
                'status':  'error',
                'message': 'No scored teams found. Make sure judges have submitted scores.'
            }), 400

        # Sort by avg_total to assign ranks
        scored.sort(key=lambda x: x['score_block']['avg_total'], reverse=True)
        for i, t in enumerate(scored):
            t['rank'] = i + 1

        # ── 2. Gemini batch call ──────────────────────────────────────
        prompt   = _build_summary_prompt(event_title, criteria, scored, event_category)
        client   = _gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            raw = raw.rsplit('```', 1)[0].strip()

        summaries = json.loads(raw)        # list of summary dicts

        # ── 3. Index by reg_id for easy lookup ───────────────────────
        summary_map = {s['reg_id']: s for s in summaries if isinstance(s, dict)}

        # ── 4. Write each summary to its registration doc ─────────────
        now_ts  = datetime.datetime.utcnow().isoformat()
        written = 0
        for t in scored:
            rid     = t['reg_id']
            summary = summary_map.get(rid)
            if not summary:
                # Fallback if Gemini missed this team
                summary = {
                    'reg_id':          rid,
                    'headline':        f"Score: {t['score_block']['avg_total']}/100",
                    'strengths':       ['Good effort', 'Completed the project'],
                    'improvements':    ['Could not be auto-summarised'],
                    'narrative':       'Summary generation encountered an issue for this team.',
                    'student_message': 'Great effort! Keep building and growing.',
                }

            summary['generated_at'] = now_ts
            summary['avg_score']    = t['score_block']['avg_total']
            summary['rank']         = t['rank']
            summary['crit_avgs']    = t['score_block']['crit_avgs']

            db.collection('registrations').document(rid).update({
                'ai_summary':   summary,
                'final_rank':   t['rank'],
                'final_score':  t['score_block']['avg_total'],
            })
            written += 1

        # ── 5. Mark event as summarised ───────────────────────────────
        db.collection('events').document(event_id).update({
            'ai_summaries_generated':    True,
            'ai_summaries_generated_at': now_ts,
            'ai_summaries_count':        written,
        })
        log_action(db, 'AI_SUMMARIES_GENERATED',
                   f'{written} summaries for event {event_id}')

        return jsonify({
            'status':    'ok',
            'count':     written,
            'summaries': [summary_map.get(t['reg_id'], {}) for t in scored],
            'teams':     scored,
        })

    except json.JSONDecodeError as exc:
        logger.error('Summary JSON parse error: %s', exc)
        return jsonify({'status': 'error',
                        'message': 'Gemini returned unreadable JSON. Please try again.'}), 500
    except Exception as exc:
        logger.error('Generate summaries error: %s', exc)
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@ai_bp.route('/summaries/<event_id>')
@login_required
@role_required(COORD_ROLES)
def get_summaries(event_id):
    """
    GET /ai/summaries/<event_id>
    Returns all saved summaries for an event (reads from registrations).
    """
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404

        event_data = event_doc.to_dict()
        criteria   = event_data.get('judging_criteria', ['Overall Score'])

        regs_raw = list(
            db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream()
        )
        results = []
        for r in regs_raw:
            d = r.to_dict()
            if d.get('is_eliminated') or not d.get('scores'):
                continue
            sb = _build_score_block(d, criteria)
            results.append({
                'reg_id':       r.id,
                'team_name':    d.get('team_name', ''),
                'lead_name':    d.get('lead_name', ''),
                'lead_email':   d.get('lead_email', ''),
                'final_rank':   d.get('final_rank'),
                'final_score':  d.get('final_score', sb['avg_total']),
                'crit_avgs':    sb['crit_avgs'],
                'ai_summary':   d.get('ai_summary'),
            })

        results.sort(key=lambda x: x.get('final_rank') or 999)
        return jsonify({
            'status':    'ok',
            'results':   results,
            'generated': event_data.get('ai_summaries_generated', False),
            'criteria':  criteria,
            'event':     {
                'id':    event_id,
                'title': event_data.get('title', ''),
                'category': event_data.get('category', ''),
            },
        })

    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@ai_bp.route('/regenerate_summary/<reg_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def regenerate_summary(reg_id):
    """
    POST /ai/regenerate_summary/<reg_id>
    Regenerates the AI summary for a single team.
    """
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            return jsonify({'status': 'error', 'message': 'Registration not found'}), 404

        reg_data   = reg_doc.to_dict()
        event_id   = reg_data.get('event_id', '')
        event_doc  = db.collection('events').document(event_id).get()
        event_data = event_doc.to_dict() if event_doc.exists else {}
        criteria   = event_data.get('judging_criteria', ['Overall Score'])

        sb   = _build_score_block(reg_data, criteria)
        proj = _project_info(reg_data)
        team = {
            'reg_id':         reg_id,
            'team_name':      reg_data.get('team_name', reg_id),
            'lead_name':      reg_data.get('lead_name', ''),
            'score_block':    sb,
            'project_title':  proj['title'],
            'project_domain': proj['domain'],
            'rank':           reg_data.get('final_rank', 1),
        }

        prompt   = _build_summary_prompt(
            event_data.get('title', 'Event'), criteria, [team],
            event_data.get('category', 'General'))
        client   = _gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            raw = raw.rsplit('```', 1)[0].strip()

        parsed   = json.loads(raw)
        summary  = parsed[0] if isinstance(parsed, list) else parsed
        summary['generated_at'] = datetime.datetime.utcnow().isoformat()
        summary['avg_score']    = sb['avg_total']
        summary['crit_avgs']    = sb['crit_avgs']

        db.collection('registrations').document(reg_id).update({
            'ai_summary': summary
        })
        log_action(db, 'AI_SUMMARY_REGEN', f'Regenerated summary for {reg_id}')
        return jsonify({'status': 'ok', 'summary': summary})

    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@ai_bp.route('/results_page/<event_id>')
@login_required
@role_required(COORD_ROLES)
def results_page(event_id):
    """GET /ai/results_page/<event_id> — full results + summaries page."""
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/coordinator/dashboard')

    event_data       = event_doc.to_dict()
    event_data['id'] = event_id
    criteria         = event_data.get('judging_criteria', ['Overall Score'])

    regs_raw = list(
        db.collection('registrations')
          .where(filter=_ff('event_id', '==', event_id))
          .stream()
    )
    results = []
    for r in regs_raw:
        d = r.to_dict()
        if d.get('is_eliminated') or not d.get('scores'):
            continue
        sb = _build_score_block(d, criteria)
        results.append({
            'reg_id':      r.id,
            'team_name':   d.get('team_name', ''),
            'lead_name':   d.get('lead_name', ''),
            'lead_email':  d.get('lead_email', ''),
            'final_rank':  d.get('final_rank'),
            'final_score': d.get('final_score', sb['avg_total']),
            'avg_score':   sb['avg_total'],
            'crit_avgs':   sb['crit_avgs'],
            'judge_count': sb['judge_count'],
            'ai_summary':  d.get('ai_summary'),
            'attendance':  d.get('attendance', 'Pending'),
        })

    results.sort(key=lambda x: (x.get('final_rank') or 999, -(x.get('avg_score') or 0)))

    return render_template(
        'coordinator/results_summary.html',
        event      = event_data,
        results    = results,
        criteria   = criteria,
        summaries_generated = event_data.get('ai_summaries_generated', False),
        user_name  = session.get('name'),
    )