"""
services_site_feedback.py — feedback about the website itself, in rounds (UPG-304)

The Super Admin makes a round from a sample form (or a blank one), edits its
questions, chooses who must answer (everyone registered for any event, lead or
team member, or the participants of chosen events) and turns it on. While a
round is on, a participant who must answer it is shown its form whenever they
open the portal, until they submit it; their ticket, signing out and the
privacy and help pages stay open (the gate in app.py). Once they have
submitted, they are never asked again for that round.

Answers are anonymous: `site_feedback_done` records that a person answered a
round (so the form stops for them), `site_feedback_answers` holds what was
answered, with no name, email or exact time, so the two can't be matched up.
A person may tick that their written answers may be quoted without a name.

Collections (stored as documents; no migration):
    site_feedback_rounds   {title, intro, questions, audience, event_ids, status, ...}
    site_feedback_answers  {round_id, answers, quote_ok, day, device, events}
    site_feedback_done     {round_id, email, day}
"""
import copy
import datetime
import hashlib
import time
import uuid

ROUNDS, ANSWERS, DONE = 'site_feedback_rounds', 'site_feedback_answers', 'site_feedback_done'

KINDS = {'rating': 'Stars, 1 to 5', 'scale': 'Score, 0 to 10', 'choice': 'Pick one', 'multi': 'Tick any',
         'text': 'Written answer'}
WITH_OPTIONS = ('choice', 'multi')
MAX_QUESTIONS = 12
TITLE_CHARS, INTRO_CHARS, LABEL_CHARS, HELP_CHARS = 120, 400, 200, 200
MAX_OPTIONS, OPTION_CHARS, ANSWER_CHARS = 10, 80, 2000

AUDIENCES = {'all': 'Everyone registered for any event (leads and team members)',
             'events': 'Only the participants of the events I choose'}
DRAFT, ON, OFF = 'draft', 'on', 'off'
STATUS_NAMES = {DRAFT: 'Not started', ON: 'On: being asked', OFF: 'Off'}
NOT_TAKING_PART = ('cancelled', 'canceled', 'refunded', 'waitlisted', 'rejected', 'withdrawn')

HONEST = ("Your answers are anonymous: we keep only that you answered, not which answers are yours. "
          "Please be honest. What didn't work helps us most.")
QUOTE_LABEL = "SapthaEvent may quote what I wrote, without my name, when telling others about the website."

RECOMMEND = {'id': 'recommend', 'kind': 'scale', 'required': True,
             'label': 'How likely are you to recommend SapthaEvent to a friend or another college?',
             'help': '0 = not at all likely, 10 = very likely', 'options': []}

# The two sample forms the Super Admin starts from. Short on purpose (about a
# minute): ratings and ticks are required, writing is optional, so nobody has
# to type "good" to get past the form. The recommend question is the same in
# both, so the two rounds can be compared.
SAMPLES = {
    'now': {
        'name': 'Sample 1: your experience so far',
        'title': 'How has SapthaEvent worked for you?',
        'intro': 'Tell us how the website has worked for you so far. It takes about a minute.',
        'questions': [
            {'id': 'signup', 'kind': 'rating', 'required': True,
             'label': 'How easy was it to sign up and register for your event?',
             'help': '1 = very hard, 5 = very easy', 'options': []},
            RECOMMEND,
            {'id': 'hard_parts', 'kind': 'multi', 'required': True,
             'label': 'Which parts were hard or confusing?', 'help': 'Tick all that apply.',
             'options': ['Creating my account or password', 'Filling in the registration form',
                         'Adding my team members', "Finding the event's details or schedule",
                         'Emails and notices', 'Using it on my phone', 'Nothing was hard']},
            {'id': 'change', 'kind': 'text', 'required': False,
             'label': 'What one thing should we change or add?', 'help': '', 'options': []},
            {'id': 'liked', 'kind': 'text', 'required': False,
             'label': 'What did you like most?', 'help': '', 'options': []},
        ]},
    'during': {
        'name': 'Sample 2: while the event is on',
        'title': 'How is the website helping you at the event?',
        'intro': 'The event is on. Tell us how the website is helping you today. It takes about a minute.',
        'questions': [
            {'id': 'find', 'kind': 'rating', 'required': True,
             'label': 'How easy is it to find what you need today: the schedule, the venue, the announcements?',
             'help': '1 = very hard, 5 = very easy', 'options': []},
            {'id': 'checkin', 'kind': 'choice', 'required': True,
             'label': 'How did check-in with your QR ticket go?', 'help': '',
             'options': ['Smooth', 'Some trouble, but it worked', "It didn't work; I was checked in by hand",
                         "I haven't checked in yet"]},
            {'id': 'updates', 'kind': 'choice', 'required': True,
             'label': "Are the organisers' updates reaching you in time?", 'help': '',
             'options': ['Yes, in time', 'Sometimes late', 'No, I missed some', "I didn't see any updates"]},
            RECOMMEND,
            {'id': 'problem', 'kind': 'text', 'required': False,
             'label': 'Is anything not working or confusing right now?', 'help': '', 'options': []},
            {'id': 'better', 'kind': 'text', 'required': False,
             'label': 'What would make the rest of the event easier?', 'help': '', 'options': []},
        ]},
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _day():
    return _now().date().isoformat()


# ── Rounds ────────────────────────────────────────────────────────────────────

_cache = {'at': 0.0, 'round': None}
CACHE_SECONDS = 30


def clear_cache():
    _cache.update(at=0.0, round=None)


def get(db, round_id):
    if not round_id:
        return None
    doc = db.collection(ROUNDS).document(str(round_id)).get()
    return dict(doc.to_dict() or {}, id=doc.id) if doc.exists else None


def rounds(db):
    rows = [dict(d.to_dict() or {}, id=d.id) for d in db.collection(ROUNDS).stream()]
    return sorted(rows, key=lambda r: str(r.get('created_at') or ''), reverse=True)


def active(db):
    """The round that is on, or None. Read at most every 30 seconds per process."""
    if time.monotonic() - _cache['at'] < CACHE_SECONDS:
        return _cache['round']
    found = None
    for r in rounds(db):
        if r.get('status') == ON:
            found = r
            break
    _cache.update(at=time.monotonic(), round=found)
    return found


def answer_count(db, round_id) -> int:
    return sum(1 for d in db.collection(DONE).stream() if (d.to_dict() or {}).get('round_id') == round_id)


def may_edit(db, r) -> bool:
    """Questions, title and who answers change only while the round is not on
    and nobody has answered (answers must mean the same questions)."""
    return r.get('status') != ON and answer_count(db, r['id']) == 0


def create(db, sample: str, by: str) -> str:
    base = SAMPLES.get(sample) or {'title': 'Website feedback', 'intro': '', 'questions': []}
    round_id = uuid.uuid4().hex
    db.collection(ROUNDS).document(round_id).set({
        'title': base['title'], 'intro': base['intro'], 'questions': copy.deepcopy(base['questions']),
        'audience': 'all', 'event_ids': [], 'status': DRAFT, 'sample': sample if sample in SAMPLES else '',
        'created_at': _now().isoformat(), 'created_by': by})
    clear_cache()
    return round_id


def copy_round(db, r, by: str) -> str:
    """A new round with the same questions, to ask again or to change them."""
    round_id = uuid.uuid4().hex
    db.collection(ROUNDS).document(round_id).set({
        'title': r.get('title') or '', 'intro': r.get('intro') or '',
        'questions': copy.deepcopy(r.get('questions') or []), 'audience': r.get('audience') or 'all',
        'event_ids': list(r.get('event_ids') or []), 'status': DRAFT, 'sample': r.get('sample') or '',
        'copied_from': r['id'], 'created_at': _now().isoformat(), 'created_by': by})
    clear_cache()
    return round_id


def delete(db, r):
    """Only a round nobody answered and that is not on."""
    if r.get('status') == ON:
        return "Turn the round off before deleting it."
    if answer_count(db, r['id']):
        return "People have answered this round, so it stays. Turn it off instead."
    db.collection(ROUNDS).document(r['id']).delete()
    clear_cache()
    return ''


def _slug(text, taken):
    base = ''.join(c if c.isalnum() else '_' for c in text.lower())[:24].strip('_') or 'q'
    slug, n = base, 2
    while slug in taken:
        slug, n = f'{base}_{n}', n + 1
    return slug


def parse_form(form, event_ids_known=()):
    """The edit form → (values, problems). Rows q_<i>_*: kind, label, help,
    options (one per line), required, remove, id; in the order of q_<i>_order."""
    problems = []
    title = (form.get('title') or '').strip()[:TITLE_CHARS]
    intro = (form.get('intro') or '').strip()[:INTRO_CHARS]
    if not title:
        problems.append('Give the round a title: participants see it at the top of the form.')
    audience = form.get('audience') if form.get('audience') in AUDIENCES else 'all'
    known = set(event_ids_known)
    event_ids = [e for e in form.getlist('event_ids') if not known or e in known] if hasattr(form, 'getlist') else []
    rows = []
    for key in form:
        if key.startswith('q_') and key.endswith('_label'):
            i = key[2:-6]
            if not i.isdigit():
                continue
            try:
                order = float(form.get(f'q_{i}_order') or i)
            except ValueError:
                order = float(i)
            rows.append((order, int(i)))
    questions, taken = [], set()
    for _, i in sorted(rows):
        label = (form.get(f'q_{i}_label') or '').strip()
        if form.get(f'q_{i}_remove') or not label:
            continue
        n = len(questions) + 1
        kind = form.get(f'q_{i}_kind') if form.get(f'q_{i}_kind') in KINDS else 'text'
        if len(label) > LABEL_CHARS:
            problems.append(f'Question {n}: at most {LABEL_CHARS} characters.')
        options = []
        if kind in WITH_OPTIONS:
            seen = set()
            for line in (form.get(f'q_{i}_options') or '').splitlines():
                line = line.strip()[:OPTION_CHARS]
                if line and line.lower() not in seen:
                    seen.add(line.lower())
                    options.append(line)
            if len(options) < 2:
                problems.append(f'Question {n} ("{label[:40]}"): give at least two choices, one per line.')
            if len(options) > MAX_OPTIONS:
                problems.append(f'Question {n}: at most {MAX_OPTIONS} choices.')
        qid = (form.get(f'q_{i}_id') or '').strip()[:40]
        if not qid or qid in taken or not all(c.isalnum() or c == '_' for c in qid):
            qid = _slug(label, taken)
        taken.add(qid)
        questions.append({'id': qid, 'kind': kind, 'label': label[:LABEL_CHARS],
                          'help': (form.get(f'q_{i}_help') or '').strip()[:HELP_CHARS],
                          'required': bool(form.get(f'q_{i}_required')), 'options': options[:MAX_OPTIONS]})
    if not questions:
        problems.append('Add at least one question.')
    if len(questions) > MAX_QUESTIONS:
        problems.append(f'At most {MAX_QUESTIONS} questions: a short form gets honest answers.')
    if audience == 'events' and not event_ids:
        problems.append('Choose at least one event, or ask everyone registered.')
    return ({'title': title, 'intro': intro, 'questions': questions, 'audience': audience,
             'event_ids': event_ids if audience == 'events' else []}, problems)


def save(db, r, values, by: str) -> str:
    if not may_edit(db, r):
        return ("People have answered this round or it is on, so it can't change. "
                "Copy it into a new round to change the questions.")
    db.collection(ROUNDS).document(r['id']).update(dict(values, updated_at=_now().isoformat(), updated_by=by))
    clear_cache()
    return ''


def turn_on(db, r, by: str) -> str:
    if r.get('status') == ON:
        return 'This round is already on.'
    other = next((o for o in rounds(db) if o.get('status') == ON and o['id'] != r['id']), None)
    if other:
        return f'Turn off “{other.get("title")}” first: one round is asked at a time.'
    if not r.get('questions'):
        return 'Add at least one question first.'
    if r.get('audience') == 'events' and not r.get('event_ids'):
        return 'Choose at least one event first, or ask everyone registered.'
    db.collection(ROUNDS).document(r['id']).update({'status': ON, 'on_at': _now().isoformat(), 'on_by': by})
    clear_cache()
    return ''


def turn_off(db, r, by: str) -> str:
    if r.get('status') != ON:
        return 'This round is not on.'
    db.collection(ROUNDS).document(r['id']).update({'status': OFF, 'off_at': _now().isoformat(), 'off_by': by})
    clear_cache()
    return ''


# ── Who must answer ───────────────────────────────────────────────────────────

def _taking_part(reg) -> bool:
    return str(reg.get('status') or '').strip().lower() not in NOT_TAKING_PART


def _emails_of(reg):
    out = {str(reg.get('lead_email') or '').strip().lower()}
    for m in reg.get('members') or []:
        if isinstance(m, dict):
            out.add(str(m.get('email') or '').strip().lower())
    out.discard('')
    return out


def _registrations(db, r):
    if r.get('audience') == 'events':
        for event_id in r.get('event_ids') or []:
            for d in db.collection('registrations').where('event_id', '==', event_id).stream():
                yield dict(d.to_dict() or {}, id=d.id)
    else:
        for d in db.collection('registrations').stream():
            yield dict(d.to_dict() or {}, id=d.id)


def events_of(db, r, email: str):
    """The registrations through which this person must answer the round."""
    email = (email or '').strip().lower()
    return [reg for reg in _registrations(db, r) if _taking_part(reg) and email in _emails_of(reg)]


def audience(db, r) -> set:
    """Everyone who must answer the round (emails)."""
    people = set()
    for reg in _registrations(db, r):
        if _taking_part(reg):
            people |= _emails_of(reg)
    return people


def _done_id(round_id, email):
    return f"{round_id}:{hashlib.sha256(email.strip().lower().encode()).hexdigest()[:40]}"


def answered(db, round_id, email) -> bool:
    return db.collection(DONE).document(_done_id(round_id, email)).get().exists


# ── The gate: is this person asked now? ───────────────────────────────────────

PARTICIPANT_ROLES = ('Student',)
RECHECK_SECONDS = 600   # someone not asked is checked again after 10 minutes (a new registration)


def must_answer(db, email: str, role: str, store: dict):
    """The round this participant must answer now, or None. `store` is the
    session: whether they're asked is kept there so most pages don't read
    the registrations again."""
    if role not in PARTICIPANT_ROLES or not email:
        return None
    r = active(db)
    if not r:
        return None
    seen = store.get('site_fb') or {}
    now = time.time()
    if seen.get('round') == r['id']:
        if seen.get('need') is False and now - float(seen.get('at') or 0) < RECHECK_SECONDS:
            return None
        if seen.get('need') is True:
            if answered(db, r['id'], email):
                store['site_fb'] = {'round': r['id'], 'need': False, 'at': now}
                return None
            return r
    need = not answered(db, r['id'], email) and bool(events_of(db, r, email))
    store['site_fb'] = {'round': r['id'], 'need': need, 'at': now}
    return r if need else None


GATE_OPEN = ('/static/', '/ticket/', '/website-feedback', '/logout', '/login', '/privacy', '/terms', '/about',
             '/health', '/offline', '/sw.js', '/manifest.webmanifest', '/favicon.ico', '/compliance/',
             '/set_password/', '/reset_password', '/forgot_password', '/reset_token/')


def gate_open(path: str) -> bool:
    """Pages a participant still opens before answering: their ticket and its
    QR, signing out, the form itself, the privacy, terms and about pages, and
    their data rights."""
    return any(path == p.rstrip('/') or path.startswith(p) for p in GATE_OPEN)


# ── Answering ─────────────────────────────────────────────────────────────────

def device_of(user_agent: str) -> str:
    ua = (user_agent or '').lower()
    if 'ipad' in ua or ('android' in ua and 'mobile' not in ua) or 'tablet' in ua:
        return 'Tablet'
    if 'mobi' in ua or 'iphone' in ua or 'android' in ua:
        return 'Phone'
    return 'Computer' if ua else ''


def read_answers(r, form):
    """The form → (answers, quote_ok, problems by question id)."""
    answers, problems = {}, {}
    for q in r.get('questions') or []:
        name, kind = f"a_{q['id']}", q['kind']
        if kind == 'multi':
            value = [o for o in form.getlist(name) if o in q['options']]
        else:
            value = (form.get(name) or '').strip()
            if kind == 'rating':
                value = int(value) if value.isdigit() and 1 <= int(value) <= 5 else ''
            elif kind == 'scale':
                value = int(value) if value.isdigit() and 0 <= int(value) <= 10 else ''
            elif kind == 'choice':
                value = value if value in q['options'] else ''
            else:
                value = value[:ANSWER_CHARS]
        if q.get('required') and value in ('', []):
            problems[q['id']] = ('Tick at least one.' if kind == 'multi' else
                                 'Write an answer.' if kind == 'text' else 'Choose an answer.')
        answers[q['id']] = value
    return answers, bool(form.get('quote_ok')), problems


def submit(db, r, email: str, answers: dict, quote_ok: bool, device: str, events: list) -> bool:
    """Saves one person's answers without who they are. False if they had
    already answered (a second tab): nothing is saved twice."""
    if answered(db, r['id'], email):
        return False
    day = _day()
    db.collection(DONE).document(_done_id(r['id'], email)).set(
        {'round_id': r['id'], 'email': email.strip().lower(), 'day': day})
    titles = sorted({str(reg.get('event_title') or '') for reg in events if reg.get('event_title')}) \
        if r.get('audience') == 'events' else []
    db.collection(ANSWERS).document(uuid.uuid4().hex).set(
        {'round_id': r['id'], 'answers': answers, 'quote_ok': bool(quote_ok), 'day': day,
         'device': device, 'events': titles})
    return True


# ── Results ───────────────────────────────────────────────────────────────────

def answers_of(db, round_id):
    rows = [d.to_dict() or {} for d in db.collection(ANSWERS).stream()]
    return sorted([a for a in rows if a.get('round_id') == round_id], key=lambda a: str(a.get('day') or ''),
                  reverse=True)


def _has_text(value):
    return isinstance(value, str) and value.strip() != ''


def results(db, r, q: str = ''):
    """Per question: counts, averages and the written answers (searched by q,
    in any case); the quotable answers; who answered by day and device."""
    rows = answers_of(db, r['id'])
    needle = (q or '').strip().lower()
    out = []
    for question in r.get('questions') or []:
        qid, kind = question['id'], question['kind']
        values = [a.get('answers', {}).get(qid) for a in rows]
        item = {'q': question, 'answered': 0}
        if kind in ('rating', 'scale'):
            nums = [v for v in values if isinstance(v, int)]
            top = 5 if kind == 'rating' else 10
            low = 1 if kind == 'rating' else 0
            item.update(answered=len(nums), average=round(sum(nums) / len(nums), 1) if nums else None,
                        spread=[(n, sum(1 for v in nums if v == n)) for n in range(top, low - 1, -1)])
            if kind == 'scale' and nums:
                promoters = sum(1 for v in nums if v >= 9)
                detractors = sum(1 for v in nums if v <= 6)
                item.update(promoters=promoters, detractors=detractors, passives=len(nums) - promoters - detractors,
                            recommend_score=round((promoters - detractors) * 100 / len(nums)))
        elif kind in WITH_OPTIONS:
            picked = [v for v in values if v not in (None, '', [])]
            item['answered'] = len(picked)
            counts = []
            for option in question['options']:
                n = sum(1 for v in picked if (option in v if isinstance(v, list) else v == option))
                counts.append((option, n, round(n * 100 / len(picked)) if picked else 0))
            item['counts'] = counts
        else:
            written = [(v, a) for v, a in zip(values, rows) if _has_text(v)]
            item['answered'] = len(written)
            item['texts'] = [{'text': v, 'quote_ok': a.get('quote_ok'), 'day': a.get('day'),
                              'device': a.get('device'), 'events': a.get('events') or []}
                             for v, a in written if not needle or needle in v.lower()]
        out.append(item)
    quotes = []
    for a in rows:
        if a.get('quote_ok'):
            for question in r.get('questions') or []:
                v = a.get('answers', {}).get(question['id'])
                if question['kind'] == 'text' and _has_text(v):
                    quotes.append({'text': v.strip(), 'question': question['label'], 'day': a.get('day')})
    devices = {}
    for a in rows:
        devices[a.get('device') or 'Not known'] = devices.get(a.get('device') or 'Not known', 0) + 1
    return {'total': len(rows), 'questions': out, 'quotes': quotes,
            'devices': sorted(devices.items(), key=lambda kv: -kv[1])}


def export_rows(db, r):
    """(columns, rows) for the CSV: one row per answer, no names."""
    questions = r.get('questions') or []
    columns = ['Day', 'Device', 'Events'] + [q['label'] for q in questions] + ['May be quoted (no name)']
    rows = []
    for a in answers_of(db, r['id']):
        cells = [a.get('day') or '', a.get('device') or '', '; '.join(a.get('events') or [])]
        for q in questions:
            v = a.get('answers', {}).get(q['id'])
            cells.append('; '.join(v) if isinstance(v, list) else ('' if v is None else v))
        cells.append('Yes' if a.get('quote_ok') else 'No')
        rows.append(cells)
    return columns, rows


# ── A person's own data (privacy) ─────────────────────────────────────────────

def own_records(db, email: str):
    """What is kept about this person: which rounds they answered (their answers
    themselves aren't linked to them, so they can't be listed or removed)."""
    email = (email or '').strip().lower()
    return [{'round_id': d.get('round_id'), 'day': d.get('day')}
            for d in (x.to_dict() or {} for x in db.collection(DONE).stream()) if d.get('email') == email]


def forget(db, email: str) -> int:
    """An account deleted: the 'answered' records go; the anonymous answers stay."""
    email = (email or '').strip().lower()
    gone = 0
    for d in db.collection(DONE).stream():
        if (d.to_dict() or {}).get('email') == email:
            db.collection(DONE).document(d.id).delete()
            gone += 1
    return gone
