"""
services_certificate_runs.py — issuing an event's certificates in the
background, in chunks, with progress and a retry (UPG-124).

A run is one bulk issue: who it covers is fixed when it starts (the people
the event owes certificates then, or only some types), split into chunks of
CHUNK_SIZE. The task `tasks.cert_tasks.issue_certificate_run` works through
the chunks not yet done and records each one's counts and failures on the run
(`certificate_runs/<run id>`), so the organiser sees done and failed counts as
it goes. Each person's certificate is issued once whatever happens
(services_certificates.issue_one and the database's unique index), so a retry
or a second run over the same people never makes a duplicate.

Without a broker the task runs inline under TASK_INLINE_TIMEOUT and carries
on in a thread past it; a run whose process stopped is retried by the
outbox's cron job (UPG-18), and only its unfinished chunks are worked again.
"""
import datetime
import logging
import os
import uuid
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

COLLECTION = 'certificate_runs'


def chunk_size() -> int:
    return max(1, int(os.environ.get('CERT_CHUNK_SIZE', '100')))


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _pair(r: dict) -> str:
    return f"{r['person_key']}|{r['cert_type']}"


def _event(db, event_id: str) -> dict:
    import services_certificates as certs
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        raise certs.CertificateError('Event not found.')
    return doc.to_dict() or {}


def ready_to_issue(event: dict) -> Optional[str]:
    """None when the event's certificates can be issued, else what's missing."""
    import services_certificates as certs
    from services_signatories import missing_message, ready
    if not certs.event_ended(event):
        return "Certificates can be issued once the event has ended."
    signatories = event.get('cert_signatories') or []
    if not ready(signatories):
        return missing_message(signatories)
    return None


def start(db, event_id: str, actor: str, kinds: Optional[Iterable[str]] = None, reason: str = 'bulk') -> dict:
    """Plan a run over everyone the event owes (or only these types) and queue it.
    Raises CertificateError when the event can't issue yet."""
    import services_certificates as certs
    from utils import log_action
    event = _event(db, event_id)
    problem = ready_to_issue(event)
    if problem:
        raise certs.CertificateError(problem)
    wanted = set(kinds) if kinds else None
    owed = [r for r in certs.recipients(db, event_id, event) if not wanted or r['cert_type'] in wanted]
    size = chunk_size()
    chunks = [{'pairs': [_pair(r) for r in owed[i:i + size]], 'status': 'pending',
               'issued': 0, 'already': 0, 'failed': 0, 'errors': []} for i in range(0, len(owed), size)]
    run_id = uuid.uuid4().hex
    run = {'event_id': event_id, 'kinds': sorted(wanted) if wanted else [], 'reason': reason,
           'status': 'queued' if chunks else 'done', 'total': len(owed), 'chunks': chunks,
           'issued': 0, 'already': 0, 'failed': 0, 'started_by': actor, 'started_at': _now(),
           'finished_at': '' if chunks else _now()}
    db.collection(COLLECTION).document(run_id).set(run)
    log_action(db, "CERT_RUN_STARTED", f"{actor}: event {event_id}, {len(owed)} certificates in {len(chunks)} "
                                       f"chunks ({reason}{', ' + ', '.join(sorted(wanted)) if wanted else ''})")
    if chunks:
        _queue(run_id)
    return dict(run, id=run_id)


def _queue(run_id: str) -> None:
    from tasks.cert_tasks import issue_certificate_run
    try:
        issue_certificate_run.delay(run_id)
    except Exception as exc:       # no broker reachable: run it here
        logger.warning("Certificate run %s not queued (%s); running inline", run_id, exc)
        work(None, run_id)


def get(db, run_id: str) -> Optional[dict]:
    doc = db.collection(COLLECTION).document(run_id).get()
    return dict(doc.to_dict() or {}, id=run_id) if doc.exists else None


def for_event(db, event_id: str) -> list:
    runs = [dict(d.to_dict() or {}, id=d.id) for d in db.collection(COLLECTION).where('event_id', '==', event_id).stream()]
    return sorted(runs, key=lambda r: r.get('started_at') or '', reverse=True)


def _totals(run: dict) -> dict:
    chunks = run.get('chunks') or []
    done = [c for c in chunks if c.get('status') in ('done', 'failed')]
    return {'issued': sum(c.get('issued', 0) for c in chunks), 'already': sum(c.get('already', 0) for c in chunks),
            'failed': sum(c.get('failed', 0) for c in chunks if c.get('status') == 'failed'),
            'chunks_done': len(done), 'chunks_total': len(chunks)}


def progress(run: dict) -> dict:
    """What the organiser sees: done and failed counts, and the failures."""
    t = _totals(run)
    errors = [e for c in run.get('chunks') or [] if c.get('status') == 'failed' for e in c.get('errors') or []]
    return dict(t, status=run.get('status'), total=run.get('total', 0), done=t['issued'] + t['already'],
                errors=errors[:50])


def work(db, run_id: str) -> dict:
    """Work through the run's unfinished chunks; return its progress."""
    import services_certificates as certs
    if db is None:
        from models import db
    run = get(db, run_id)
    if not run:
        raise certs.CertificateError('No such certificate run.')
    event_id = run['event_id']
    event = _event(db, event_id)
    ref = db.collection(COLLECTION).document(run_id)
    ref.update({'status': 'running'})
    by_pair = {_pair(r): r for r in certs.recipients(db, event_id, event)}
    chunks = run['chunks']
    for index, chunk in enumerate(chunks):
        if chunk.get('status') == 'done':
            continue
        counts = {'issued': 0, 'already': 0, 'failed': 0}
        errors = []
        for pair in chunk['pairs']:
            r = by_pair.get(pair)
            if r is None:                      # no longer owed (e.g. marked absent since): nothing to issue
                counts['already'] += 1
                continue
            try:
                counts['issued' if certs.issue_one(event_id, event, r, run.get('started_by', '')) else 'already'] += 1
            except Exception as exc:
                logger.exception("Certificate %s at %s failed", pair, event_id)
                counts['failed'] += 1
                errors.append({'name': r.get('name', ''), 'type': r['cert_type'], 'error': str(exc)[:200]})
        # A retried chunk keeps what it issued before (those now come back as "already")
        issued = (chunk.get('issued', 0) if chunk.get('status') == 'failed' else 0) + counts['issued']
        chunk.update(issued=issued, failed=counts['failed'], already=len(chunk['pairs']) - issued - counts['failed'],
                     errors=errors, status='failed' if counts['failed'] else 'done')
        chunks[index] = chunk
        ref.update(dict({'chunks': chunks}, **_totals(run)))
    t = _totals(run)
    status = 'failed' if t['failed'] else 'done'
    ref.update(dict(t, status=status, finished_at=_now()))
    run.update(t, status=status)
    logger.info("Certificate run %s for %s: %s", run_id, event_id, t)
    return progress(run)


def retry(db, run_id: str, actor: str) -> Optional[dict]:
    """Queue the run's failed chunks again (nothing already issued is issued twice)."""
    import services_certificates as certs
    from utils import log_action
    run = get(db, run_id)
    if not run:
        raise certs.CertificateError('No such certificate run.')
    failed = [c for c in run.get('chunks') or [] if c.get('status') == 'failed']
    if not failed:
        raise certs.CertificateError('Nothing in this run failed.')
    problem = ready_to_issue(_event(db, run['event_id']))
    if problem:
        raise certs.CertificateError(problem)
    db.collection(COLLECTION).document(run_id).update({'status': 'queued'})
    log_action(db, "CERT_RUN_RETRIED", f"{actor}: run {run_id} of event {run['event_id']} ({len(failed)} chunks)")
    _queue(run_id)
    return get(db, run_id)


def on_results_published(db, event_id: str, actor: str) -> Optional[str]:
    """Issue the position certificates when results are published, unless the
    organiser switched it off. Returns a note for the publisher, or None."""
    import services_certificates as certs
    try:
        event = _event(db, event_id)
        if event.get('cert_auto_issue') is False:
            return None
        problem = ready_to_issue(event)
        if problem:
            return f"Position certificates weren't issued: {problem}"
        run = start(db, event_id, actor, kinds=certs.POSITION_TYPES, reason='results published')
        return f"Issuing {run['total']} position certificates." if run['total'] else None
    except Exception as exc:
        logger.exception("Automatic certificates for %s failed", event_id)
        return f"Position certificates weren't issued: {exc}"
