"""
services_interact.py — live polls and audience Q&A (UPG-160).

The event's check-in staff host: they open and close polls (single or
multiple choice) and moderate questions. Attendees who were checked in to the
event (the lead or a member of a Present registration) answer each poll once
and upvote each question once; the database keys make "once" hold when two
taps arrive together. A poll or question may belong to one agenda session
(UPG-159) or to the whole event.

When the event's Q&A is moderated (`event['qa_moderated']`), a new question
is pending until the host shows it. Pending and hidden questions never reach
the projector. All text is stored as typed and escaped where it's shown.
"""
import datetime as _dt
import json
import secrets
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
MAX_OPTIONS = 8
QUESTION_STATUSES = ('pending', 'visible', 'answered', 'hidden')
ON_SCREEN = ('visible', 'answered')


class InteractError(ValueError):
    """A reason to refuse, shown to the person as it is."""


def _session():
    from db_pg import get_session
    return get_session()


def _now() -> str:
    return _dt.datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')


def checked_in(db, event_id: str, email: str) -> bool:
    """Whether this person is the lead or a member of a registration marked
    Present for the event."""
    email = (email or '').strip().lower()
    if not email:
        return False
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        if str(reg.get('attendance') or '').strip().lower() != 'present':
            continue
        people = {(reg.get('lead_email') or '').lower()}
        people |= {(m.get('email') or '').lower() for m in reg.get('members') or []}
        if email in people:
            return True
    return False


# ── Polls ──────────────────────────────────────────────────────────────────

def create_poll(event_id: str, question: str, options: List[str], multiple: bool = False,
                session_id: str = '') -> str:
    from models_pg import LivePoll
    question = (question or '').strip()[:300]
    options = [o.strip()[:120] for o in options if o and o.strip()][:MAX_OPTIONS]
    if not question:
        raise InteractError('Write the question.')
    if len(options) < 2:
        raise InteractError('Give at least two options.')
    poll_id = 'p' + secrets.token_hex(6)
    with _session() as s:
        s.add(LivePoll(id=poll_id, event_id=str(event_id), session_id=session_id or '', question=question,
                       options_json=json.dumps(options), multiple=bool(multiple), status='open',
                       created_at=_now()))
    return poll_id


def get_poll(poll_id: str) -> Optional[Dict]:
    from models_pg import LivePoll
    with _session() as s:
        row = s.get(LivePoll, str(poll_id))
        return _poll_dict(row) if row else None


def _poll_dict(row) -> Dict:
    return {'id': row.id, 'event_id': row.event_id, 'session_id': row.session_id, 'question': row.question,
            'options': json.loads(row.options_json or '[]'), 'multiple': bool(row.multiple),
            'status': row.status, 'created_at': row.created_at}


def set_poll_status(poll_id: str, status: str) -> None:
    from models_pg import LivePoll
    if status not in ('open', 'closed'):
        raise InteractError('Unknown poll state.')
    with _session() as s:
        row = s.get(LivePoll, str(poll_id))
        if row is not None:
            row.status = status


def vote(poll: Dict, email: str, choices: List[str]) -> bool:
    """Record the person's answer. False when they had already answered."""
    from models_pg import LivePollVote
    if poll['status'] != 'open':
        raise InteractError('This poll is closed.')
    picked = sorted({int(c) for c in choices if str(c).lstrip('-').isdigit()})
    if not picked or any(c < 0 or c >= len(poll['options']) for c in picked):
        raise InteractError('Choose an option.')
    if len(picked) > 1 and not poll['multiple']:
        raise InteractError('Choose one option.')
    try:
        with _session() as s:
            s.add(LivePollVote(key=f"{poll['id']}:{(email or '').lower()}", poll_id=poll['id'],
                               choices_json=json.dumps(picked)))
        return True
    except IntegrityError:
        return False


def has_voted(poll_id: str, email: str) -> bool:
    from models_pg import LivePollVote
    with _session() as s:
        return s.get(LivePollVote, f"{poll_id}:{(email or '').lower()}") is not None


def results(poll: Dict) -> Dict:
    """{'votes': people who answered, 'counts': [per option]}."""
    from models_pg import LivePollVote
    counts = [0] * len(poll['options'])
    voters = 0
    with _session() as s:
        for (raw,) in s.query(LivePollVote.choices_json).filter(LivePollVote.poll_id == poll['id']):
            voters += 1
            for c in json.loads(raw or '[]'):
                if 0 <= c < len(counts):
                    counts[c] += 1
    return {'votes': voters, 'counts': counts}


def polls_for(event_id: str, status: Optional[str] = None) -> List[Dict]:
    from models_pg import LivePoll
    with _session() as s:
        q = s.query(LivePoll).filter(LivePoll.event_id == str(event_id))
        if status:
            q = q.filter(LivePoll.status == status)
        return [_poll_dict(r) for r in q.order_by(LivePoll.created_at, LivePoll.id)]


# ── Questions ──────────────────────────────────────────────────────────────

def ask(event_id: str, email: str, text: str, moderated: bool, session_id: str = '') -> str:
    from models_pg import LiveQuestion
    text = (text or '').strip()
    if not text:
        raise InteractError('Write your question.')
    if len(text) > 500:
        raise InteractError('Keep the question under 500 characters.')
    qid = 'q' + secrets.token_hex(6)
    with _session() as s:
        s.add(LiveQuestion(id=qid, event_id=str(event_id), session_id=session_id or '', text=text,
                           asked_by=(email or '').lower(), status='pending' if moderated else 'visible',
                           created_at=_now()))
    return qid


def get_question(qid: str) -> Optional[Dict]:
    from models_pg import LiveQuestion
    with _session() as s:
        row = s.get(LiveQuestion, str(qid))
        return _question_dict(row) if row else None


def _question_dict(row, votes: int = 0) -> Dict:
    return {'id': row.id, 'event_id': row.event_id, 'session_id': row.session_id, 'text': row.text,
            'asked_by': row.asked_by, 'status': row.status, 'created_at': row.created_at, 'votes': votes}


def set_question_status(qid: str, status: str) -> None:
    from models_pg import LiveQuestion
    if status not in QUESTION_STATUSES:
        raise InteractError('Unknown question state.')
    with _session() as s:
        row = s.get(LiveQuestion, str(qid))
        if row is not None:
            row.status = status


def upvote(question: Dict, email: str) -> bool:
    """Count the person's upvote once. False when they had already upvoted."""
    from models_pg import LiveQuestionVote
    if question['status'] not in ON_SCREEN:
        raise InteractError("This question isn't open for votes.")
    try:
        with _session() as s:
            s.add(LiveQuestionVote(key=f"{question['id']}:{(email or '').lower()}", question_id=question['id']))
        return True
    except IntegrityError:
        return False


def questions_for(event_id: str, statuses=ON_SCREEN) -> List[Dict]:
    """The event's questions in these states, most upvoted first."""
    from models_pg import LiveQuestion, LiveQuestionVote
    with _session() as s:
        rows = s.query(LiveQuestion).filter(LiveQuestion.event_id == str(event_id),
                                            LiveQuestion.status.in_(list(statuses))).all()
        ids = [r.id for r in rows]
        votes = dict(s.query(LiveQuestionVote.question_id, func.count(LiveQuestionVote.key))
                     .filter(LiveQuestionVote.question_id.in_(ids)).group_by(LiveQuestionVote.question_id)) if ids else {}
        out = [_question_dict(r, votes.get(r.id, 0)) for r in rows]
    out.sort(key=lambda q: (q['status'] == 'answered', -q['votes'], q['created_at']))
    return out


# ── The projector and the report ───────────────────────────────────────────

def screen_snapshot(event_id: str) -> Dict:
    """What the projector shows: open polls with their counts (or, with none
    open, the last closed one), and the questions on screen."""
    polls = polls_for(event_id)
    shown = [p for p in polls if p['status'] == 'open'] or polls[-1:]
    return {'polls': [dict(p, **results(p)) for p in shown],
            'questions': [{k: q[k] for k in ('id', 'text', 'votes', 'status')} for q in questions_for(event_id)]}
