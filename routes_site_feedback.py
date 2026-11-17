"""
routes_site_feedback.py — website feedback rounds (UPG-304)

    /website-feedback                          the participant's form (the gate sends them here)
    /admin/website-feedback                    the Super Admin's rounds, new from a sample
    /admin/website-feedback/<id>               edit, turn on or off, results
    /admin/website-feedback/<id>/answers.csv   the answers, no names

The gate that sends participants to the form is `site_feedback_gate` in app.py.
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session

import services_site_feedback as sf
from models import db
from utils import log_action, login_required, role_required

site_feedback_bp = Blueprint('site_feedback', __name__)
SUPER_ROLES = ['SuperAdmin', 'Super Admin', 'UniversityAdmin']
ENDED = ('completed', 'certified', 'archived', 'cancelled')


def _safe_next(value: str) -> str:
    value = (value or '').strip()
    if not value.startswith('/') or value.startswith('//') or '\\' in value or value.startswith('/website-feedback'):
        return '/participant/dashboard'
    return value[:500]


def _tickets(email):
    """The person's tickets, so the form never stands between them and the gate."""
    from services_privacy import registrations_of
    out = []
    for reg_id, reg in registrations_of(db, email):
        if sf._taking_part(reg):
            out.append({'id': reg_id, 'title': reg.get('event_title') or 'Your event'})
    return out[:6]


@site_feedback_bp.route('/website-feedback', methods=['GET', 'POST'])
@login_required
def answer():
    email = str(session.get('user_id') or '')
    nxt = _safe_next(request.values.get('next'))
    r = sf.must_answer(db, email, session.get('role', ''), session)
    if not r:
        session.modified = True
        return redirect(nxt)
    answers, quote_ok, problems = {}, False, {}
    if request.method == 'POST':
        answers, quote_ok, problems = sf.read_answers(r, request.form)
        if not problems:
            regs = sf.events_of(db, r, email)
            sf.submit(db, r, email, answers, quote_ok, sf.device_of(request.headers.get('User-Agent', '')), regs)
            session['site_fb'] = {'round': r['id'], 'need': False, 'at': __import__('time').time()}
            flash('Thank you. Your feedback was sent, and you won\'t be asked this again.', 'success')
            return redirect(nxt)
    return render_template('site_feedback/answer.html', r=r, answers=answers, quote_ok=quote_ok,
                           problems=problems, nxt=nxt, tickets=_tickets(email), honest=sf.HONEST,
                           quote_label=sf.QUOTE_LABEL), (400 if problems else 200)


# ── The Super Admin ───────────────────────────────────────────────────────────

def _round_or_404(round_id):
    r = sf.get(db, round_id)
    if not r:
        abort(404)
    return r


def _open_events():
    rows = []
    for d in db.collection('events').stream():
        e = d.to_dict() or {}
        if str(e.get('status') or '').lower() in ENDED:
            continue
        rows.append({'id': d.id, 'title': e.get('title') or e.get('name') or 'Untitled', 'date': str(e.get('date') or '')})
    return sorted(rows, key=lambda e: (e['date'], e['title']))


@site_feedback_bp.route('/admin/website-feedback')
@login_required
@role_required(SUPER_ROLES)
def rounds():
    rows = sf.rounds(db)
    for r in rows:
        r['answers'] = sf.answer_count(db, r['id'])
    return render_template('site_feedback/rounds.html', rounds=rows, samples=sf.SAMPLES,
                           status_names=sf.STATUS_NAMES, current_page='website_feedback')


@site_feedback_bp.route('/admin/website-feedback/new', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def new_round():
    sample = request.form.get('sample') or ''
    round_id = sf.create(db, sample, session.get('user_id', ''))
    log_action(db, 'SITE_FEEDBACK_ROUND_CREATED', f"{session.get('user_id')} made website feedback round {round_id}"
               + (f" from sample '{sample}'" if sample in sf.SAMPLES else ' (blank)'))
    flash('Round made. Check the questions and who answers, then turn it on.', 'success')
    return redirect(f'/admin/website-feedback/{round_id}')


@site_feedback_bp.route('/admin/website-feedback/<round_id>', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def edit(round_id):
    r = _round_or_404(round_id)
    events = _open_events()
    values, problems = r, []
    if request.method == 'POST':
        values, problems = sf.parse_form(request.form, [e['id'] for e in events] + list(r.get('event_ids') or []))
        if not problems:
            refusal = sf.save(db, r, values, session.get('user_id', ''))
            if refusal:
                flash(refusal, 'danger')
            else:
                log_action(db, 'SITE_FEEDBACK_ROUND_SAVED',
                           f"{session.get('user_id')} saved website feedback round {round_id}")
                flash('Saved.', 'success')
            return redirect(f'/admin/website-feedback/{round_id}')
        values = dict(r, **values)
        flash('Nothing was saved. Fix what is marked below.', 'danger')
    q = (request.args.get('q') or '').strip()
    chosen = {e['id'] for e in events}
    gone = [{'id': e, 'title': 'An event that has ended', 'date': ''} for e in r.get('event_ids') or [] if e not in chosen]
    return render_template('site_feedback/round.html', r=r, values=values, problems=problems,
                           editable=sf.may_edit(db, r), events=events + gone, kinds=sf.KINDS,
                           audiences=sf.AUDIENCES, status_names=sf.STATUS_NAMES,
                           result=sf.results(db, r, q), q=q, asked=len(sf.audience(db, r)),
                           done=sf.answer_count(db, r['id']), max_questions=sf.MAX_QUESTIONS,
                           with_options=sf.WITH_OPTIONS, honest=sf.HONEST, quote_label=sf.QUOTE_LABEL,
                           current_page='website_feedback'), (400 if problems else 200)


@site_feedback_bp.route('/admin/website-feedback/<round_id>/preview')
@login_required
@role_required(SUPER_ROLES)
def preview(round_id):
    """The form as participants see it; nothing can be sent from here."""
    r = _round_or_404(round_id)
    return render_template('site_feedback/answer.html', r=r, answers={}, quote_ok=False, problems={},
                           nxt='/admin/website-feedback', tickets=[], honest=sf.HONEST,
                           quote_label=sf.QUOTE_LABEL, preview=True)


@site_feedback_bp.route('/admin/website-feedback/<round_id>/<action>', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def act(round_id, action):
    r = _round_or_404(round_id)
    by = session.get('user_id', '')
    if action == 'on':
        refusal = sf.turn_on(db, r, by)
        done = 'On. Participants who must answer see the form the next time they open the portal.'
    elif action == 'off':
        refusal = sf.turn_off(db, r, by)
        done = 'Off. Nobody is asked any more; the answers stay.'
    elif action == 'copy':
        new_id = sf.copy_round(db, r, by)
        log_action(db, 'SITE_FEEDBACK_ROUND_COPIED', f"{by} copied website feedback round {round_id} to {new_id}")
        flash('Copied into a new round. Change it, then turn it on.', 'success')
        return redirect(f'/admin/website-feedback/{new_id}')
    elif action == 'delete':
        refusal = sf.delete(db, r)
        if not refusal:
            log_action(db, 'SITE_FEEDBACK_ROUND_DELETED', f"{by} deleted website feedback round {round_id}")
            flash('Deleted.', 'success')
            return redirect('/admin/website-feedback')
        done = ''
    else:
        abort(404)
    if refusal:
        flash(refusal, 'danger')
    else:
        log_action(db, f'SITE_FEEDBACK_ROUND_{action.upper()}', f"{by} turned website feedback round {round_id} {action}")
        flash(done, 'success')
    return redirect(f'/admin/website-feedback/{round_id}')


@site_feedback_bp.route('/admin/website-feedback/<round_id>/answers.csv')
@login_required
@role_required(SUPER_ROLES)
def export(round_id):
    import services_export
    r = _round_or_404(round_id)
    columns, rows = sf.export_rows(db, r)
    return Response(services_export.to_csv(rows, columns), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=Website-feedback.csv'})
