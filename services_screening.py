"""
services_screening.py — an online screening round for an event's waitlist
(UPG-238).

When more people wait than there are seats, the hosting SPOC writes a short
round of multiple-choice questions, each with its right answer and points,
and when it opens and closes (and, if they like, a time limit). Opening it
tells everyone waiting. Each team's lead answers once for the team, between
the times; the answers are scored on submit by the right answers, the same
way for everyone. The SPOC's waitlist shows each score, sorts by it, and
"Accept the top N" accepts the N best (a tie goes to whoever joined the
waitlist earlier). Those not accepted stay waiting and are not told
(D-13, as proposed and approved by the owner on 2026-11-12).

Stored on the event as `screening`:
    {questions: [{id, text, options: [...], answer: index, points}],
     opens_at, closes_at (UTC ISO), minutes (0 = no limit),
     published: bool, published_at, published_by}
Each answer sheet is a `screening_answers` document `{event_id}__{wl_id}`:
    {event_id, wl_id, email, started_at, submitted_at, answers: {qid: index},
     score, max_score, late}
The right answers never leave the server: the page that asks the questions
gets only the text and the choices.
"""
import datetime
import logging
import uuid

logger = logging.getLogger(__name__)

SHEETS = 'screening_answers'
MAX_QUESTIONS = 50
MAX_OPTIONS = 6
TEXT_MAX = 500
OPTION_MAX = 200
MAX_MINUTES = 300
MAX_POINTS = 100
GRACE = datetime.timedelta(minutes=1)   # for a slow connection on the last click


class ScreeningError(Exception):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(when) -> str:
    return when.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')


def _parse(value):
    from services_hackathon import parse_iso
    return parse_iso(value)


def _norm(value) -> str:
    return str(value or '').strip().lower()


# ── The round ───────────────────────────────────────────────────────────────

def round_of(event: dict) -> dict:
    s = (event or {}).get('screening')
    s = dict(s) if isinstance(s, dict) else {}
    s['questions'] = [q for q in s.get('questions') or [] if isinstance(q, dict) and q.get('id')]
    return s


def max_score(s: dict) -> int:
    return sum(int(q.get('points') or 0) for q in s.get('questions') or [])


def window(s: dict, now=None) -> str:
    """'draft' (not opened by the SPOC), 'upcoming', 'open' or 'closed'."""
    if not s.get('published'):
        return 'draft'
    now = now or _now()
    opens, closes = _parse(s.get('opens_at')), _parse(s.get('closes_at'))
    if opens and now < opens:
        return 'upcoming'
    if closes and now > closes:
        return 'closed'
    return 'open'


def _save(db, event_id: str, event: dict, s: dict) -> None:
    db.collection('events').document(str(event_id)).update({'screening': s})
    event['screening'] = s


def _locked(db, event_id: str, s: dict) -> bool:
    """Questions can't change once the round is open to people, or anyone answered."""
    return bool(s.get('published')) or bool(sheets(db, event_id))


def add_question(db, event_id: str, event: dict, form) -> str:
    """Add the question the SPOC typed. Returns the message, or ScreeningError."""
    s = round_of(event)
    if _locked(db, event_id, s):
        raise ScreeningError("The round is open, so its questions can't change: it must be the same for everyone.")
    text = ' '.join(str(form.get('text') or '').split())[:TEXT_MAX]
    options = [' '.join(str(form.get(f'option_{i}') or '').split())[:OPTION_MAX] for i in range(1, MAX_OPTIONS + 1)]
    right = str(form.get('answer') or '').strip()
    if not text:
        raise ScreeningError("Type the question.")
    chosen = [(i, o) for i, o in enumerate(options, start=1) if o]
    if len(chosen) < 2:
        raise ScreeningError("Give at least two choices.")
    if not right.isdigit() or not options[int(right) - 1:int(right)] or not options[int(right) - 1]:
        raise ScreeningError("Choose which choice is the right answer.")
    try:
        points = int(str(form.get('points') or '1').strip())
    except ValueError:
        points = -1
    if not 1 <= points <= MAX_POINTS:
        raise ScreeningError(f"Points must be a whole number from 1 to {MAX_POINTS}.")
    if len(s['questions']) >= MAX_QUESTIONS:
        raise ScreeningError(f"A round can have {MAX_QUESTIONS} questions.")
    kept = [o for _, o in chosen]
    answer = [i for i, _ in chosen].index(int(right))
    s['questions'] = s['questions'] + [{'id': uuid.uuid4().hex[:10], 'text': text, 'options': kept,
                                        'answer': answer, 'points': points}]
    _save(db, event_id, event, s)
    return f"Question {len(s['questions'])} is added."


def remove_question(db, event_id: str, event: dict, qid: str) -> str:
    s = round_of(event)
    if _locked(db, event_id, s):
        raise ScreeningError("The round is open, so its questions can't change: it must be the same for everyone.")
    kept = [q for q in s['questions'] if q.get('id') != qid]
    if len(kept) == len(s['questions']):
        raise ScreeningError("That question isn't in the round any more.")
    s['questions'] = kept
    _save(db, event_id, event, s)
    return "The question is removed."


def set_times(db, event_id: str, event: dict, form) -> str:
    """When the round opens and closes (the event's local time), and the time limit."""
    from services_hackathon import parse_local, show
    s = round_of(event)
    opens = parse_local(form.get('opens_at'), event)
    closes = parse_local(form.get('closes_at'), event)
    if not opens or not closes:
        raise ScreeningError("Give the date and time the round opens and closes.")
    if closes <= opens:
        raise ScreeningError("The round must close after it opens.")
    try:
        minutes = int(str(form.get('minutes') or '0').strip() or 0)
    except ValueError:
        minutes = -1
    if not 0 <= minutes <= MAX_MINUTES:
        raise ScreeningError(f"The time limit is in minutes, from 1 to {MAX_MINUTES}, or empty for none.")
    s.update(opens_at=_iso(opens), closes_at=_iso(closes), minutes=minutes)
    _save(db, event_id, event, s)
    return (f"The round opens {show(s['opens_at'], event)} and closes {show(s['closes_at'], event)}"
            + (f", {minutes} minutes each." if minutes else ", with no time limit."))


def publish(db, event_id: str, event: dict, by: str) -> dict:
    """Open the round to everyone waiting, and tell each waiting lead.
    Returns {'told', 'emailed', 'limit'}."""
    s = round_of(event)
    if s.get('published'):
        raise ScreeningError("The round is already open to people waiting.")
    if not s['questions']:
        raise ScreeningError("Add at least one question first.")
    if not s.get('opens_at') or not s.get('closes_at'):
        raise ScreeningError("Set when the round opens and closes first.")
    if _parse(s['closes_at']) <= _now():
        raise ScreeningError("The closing time has passed: set a later one first.")
    s.update(published=True, published_at=_iso(_now()), published_by=by)
    _save(db, event_id, event, s)
    return invite(db, event_id, event, by)


def invite(db, event_id: str, event: dict, by: str = '') -> dict:
    """A portal notice and one email to each lead still waiting: the round, its
    times and the link. The email is about getting a seat, so it goes as the
    registration emails do (also in a portal-mode hackathon), counted in the
    daily limit."""
    import services_hackathon as hk
    from routes_notifications_v2 import create_notification
    from services_hackathon import show
    from services_waitlist import waiting
    from utils_email import _base_url
    s = round_of(event)
    title = event.get('title') or 'the event'
    link = f"/participant/screening/{event_id}"
    when = f"It opens {show(s.get('opens_at'), event)} and closes {show(s.get('closes_at'), event)}."
    size = len(s['questions'])
    limit = f" You have {s['minutes']} minutes once you start." if s.get('minutes') else ''
    told = emailed = 0
    over = False
    for _, entry in waiting(db, event_id):
        lead = _norm(entry.get('user_email') or entry.get('email'))
        if not lead:
            continue
        try:
            create_notification(db, user_email=lead, notif_type='screening_round',
                                title=f"A screening round for the waitlist of {title}",
                                message=f"{when}{limit} Answer it once, for your team.", link=link,
                                metadata={'event_id': str(event_id)})
            told += 1
        except Exception:
            logger.warning("Screening notice to %s failed", lead, exc_info=True)
        if over or not hk.email_allowed(event, 'registration'):
            continue
        reg = entry.get('reg_data') if isinstance(entry.get('reg_data'), dict) else {}
        name = reg.get('lead_name') or entry.get('name') or 'there'
        text = (f"Hi {name},\n\n"
                f"More people are waiting for {title} than there are seats, so the organiser is "
                f"holding a short online screening round for everyone on the waitlist.\n\n"
                f"{when}{limit}\n"
                f"There {'is' if size == 1 else 'are'} {size} multiple-choice question{'' if size == 1 else 's'}. "
                f"You answer once{', for your team' if reg.get('team_name') else ''}.\n\n"
                f"Take it here (log in first): {_base_url()}{link}\n")
        from services_seat_email import _send
        sent = _send(db, lead, f"Screening round for the waitlist of {title}", text, event, by)
        if sent['status'] == 'sent':
            emailed += 1
        elif sent['status'] == 'limit':
            over = True
    return {'told': told, 'emailed': emailed, 'limit': over}


def close_now(db, event_id: str, event: dict) -> str:
    s = round_of(event)
    if window(s) not in ('open', 'upcoming'):
        raise ScreeningError("The round isn't open.")
    s['closes_at'] = _iso(_now())
    _save(db, event_id, event, s)
    return "The round is closed; nobody else can answer."


# ── Answer sheets ───────────────────────────────────────────────────────────

def _sheet_id(event_id: str, wl_id: str) -> str:
    return f"{event_id}__{wl_id}"


def sheet(db, event_id: str, wl_id: str):
    doc = db.collection(SHEETS).document(_sheet_id(event_id, wl_id)).get()
    return (doc.to_dict() or {}) if doc.exists else None


def sheets(db, event_id: str) -> dict:
    """{wl_id: sheet} of the event's submitted answer sheets."""
    out = {}
    for d in db.collection(SHEETS).where('event_id', '==', str(event_id)).stream():
        data = d.to_dict() or {}
        if data.get('submitted_at') and data.get('wl_id'):
            out[str(data['wl_id'])] = data
    return out


def entry_for(db, event_id: str, email: str):
    """(wl_id, entry) of this lead's waiting entry for the event, or (None, None)."""
    from services_waitlist import waiting
    email = _norm(email)
    for wl_id, entry in waiting(db, event_id):
        if _norm(entry.get('user_email') or entry.get('email')) == email:
            return wl_id, entry
    return None, None


def member_of(db, event_id: str, email: str):
    """The waiting entry whose team lists this person as a member (not the lead)."""
    from services_waitlist import waiting
    email = _norm(email)
    for wl_id, entry in waiting(db, event_id):
        reg = entry.get('reg_data') if isinstance(entry.get('reg_data'), dict) else {}
        if any(_norm((m or {}).get('email')) == email for m in reg.get('members') or [] if isinstance(m, dict)):
            return wl_id, entry
    return None, None


def deadline(s: dict, started_at) -> datetime.datetime | None:
    """When this person must submit by: the time limit from when they
    started, or the round's close, whichever comes first."""
    closes = _parse(s.get('closes_at'))
    started = _parse(started_at)
    ends = [t for t in (closes, started + datetime.timedelta(minutes=int(s.get('minutes') or 0))
                        if started and s.get('minutes') else None) if t]
    return min(ends) if ends else None


def start(db, event_id: str, wl_id: str, email: str) -> dict:
    """The person opens the questions: their clock starts once (a reload
    doesn't restart it)."""
    ref = db.collection(SHEETS).document(_sheet_id(event_id, wl_id))
    doc = ref.get()
    if doc.exists:
        return doc.to_dict() or {}
    data = {'event_id': str(event_id), 'wl_id': str(wl_id), 'email': _norm(email),
            'started_at': _iso(_now()), 'submitted_at': '', 'answers': {}, 'score': 0, 'max_score': 0,
            'late': False}
    ref.set(data)
    return data


def questions_for_taker(s: dict) -> list:
    """The questions as the person sees them: no right answers, no points needed."""
    return [{'id': q['id'], 'text': q.get('text') or '', 'options': list(q.get('options') or []),
             'points': int(q.get('points') or 0)} for q in s.get('questions') or []]


def submit(db, event_id: str, event: dict, wl_id: str, email: str, form) -> dict:
    """Score the answers once. Returns the sheet, or ScreeningError."""
    s = round_of(event)
    state = window(s)
    if state != 'open' and not (state == 'closed' and _parse(s.get('closes_at'))
                                and _now() <= _parse(s.get('closes_at')) + GRACE):
        raise ScreeningError("The screening round isn't open." if state != 'closed'
                             else "The screening round has closed.")
    ref = db.collection(SHEETS).document(_sheet_id(event_id, wl_id))
    doc = ref.get()
    data = (doc.to_dict() or {}) if doc.exists else start(db, event_id, wl_id, email)
    if data.get('submitted_at'):
        raise ScreeningError("Your answers were already received; the round is answered once.")
    now = _now()
    ends = deadline(s, data.get('started_at'))
    late = bool(ends and now > ends + GRACE)
    answers = {}
    for q in s['questions']:
        raw = str(form.get(f"q_{q['id']}") or '').strip()
        if raw.isdigit() and int(raw) < len(q.get('options') or []):
            answers[q['id']] = int(raw)
    score = 0 if late else sum(int(q.get('points') or 0) for q in s['questions']
                                if answers.get(q['id']) == int(q.get('answer', -1)))
    data.update(answers=answers, score=score, max_score=max_score(s), submitted_at=_iso(now), late=late)
    ref.set(data)
    return data


# ── The ranking ─────────────────────────────────────────────────────────────

def ranking(db, event_id: str) -> list:
    """[(wl_id, entry, sheet)] of everyone still waiting who answered, best
    first; a tie goes to whoever joined the waitlist earlier (D-13)."""
    from services_waitlist import waiting
    done = sheets(db, event_id)
    line = [(wl_id, entry, done[wl_id]) for wl_id, entry in waiting(db, event_id) if wl_id in done]
    # waiting() is in join order already; a stable sort keeps it within a score
    return sorted(line, key=lambda row: -int(row[2].get('score') or 0))


def annotate_rows(db, event: dict, rows: list) -> dict:
    """Adds score, max, rank and submitted to the SPOC's waitlist rows. Returns
    a summary for the page: {on, state, answered, waiting, max}."""
    s = round_of(event)
    if not s['questions'] and not s.get('published'):
        return {'on': False}
    done = sheets(db, event['id'])
    ranks = {wl_id: i for i, (wl_id, _, _) in enumerate(ranking(db, event['id']), start=1)}
    for row in rows:
        got = done.get(row['id'])
        row['screening'] = ({'score': int(got.get('score') or 0), 'max': int(got.get('max_score') or 0),
                             'late': bool(got.get('late')), 'rank': ranks.get(row['id'])} if got else None)
    return {'on': True, 'state': window(s), 'answered': sum(1 for r in rows if r.get('screening')),
            'waiting': len(rows), 'max': max_score(s)}


def card(db, event: dict, row: dict, email: str):
    """What a person's waitlist card says about the round (UPG-236's card), or None."""
    from services_hackathon import show
    s = round_of(event)
    state = window(s)
    if state == 'draft' or row.get('state') != 'waiting':
        return None
    info = {'state': state, 'opens': show(s.get('opens_at'), event), 'closes': show(s.get('closes_at'), event),
            'minutes': int(s.get('minutes') or 0), 'link': f"/participant/screening/{row['event_id']}",
            'is_lead': bool(row.get('is_lead')), 'done': False}
    got = sheet(db, row['event_id'], row['id'])     # the team's one sheet, lead or member
    info['done'] = bool(got and got.get('submitted_at'))
    return info


def annotate_standing(db, rows: list, email: str) -> list:
    """Adds the round, if any, to each waiting row of services_waitlist.standing."""
    events = {}
    for row in rows:
        if row.get('state') != 'waiting':
            continue
        event_id = row['event_id']
        if event_id not in events:
            doc = db.collection('events').document(event_id).get()
            events[event_id] = dict(doc.to_dict() or {}, id=event_id) if doc.exists else None
        if events[event_id]:
            row['screening'] = card(db, events[event_id], row, email)
    return rows
