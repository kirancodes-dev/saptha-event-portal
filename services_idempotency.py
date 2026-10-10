"""
services_idempotency.py — a form sent twice is handled once (UPG-26).

The registration form carries a random hidden `submission_id`. The first
request to arrive claims it with a unique insert; any other request with the
same key (a double click, a resend on a slow network) sees it's taken and is
sent to the result of the first instead of registering again.
"""
import datetime
import logging

logger = logging.getLogger(__name__)
KEEP = datetime.timedelta(days=2)


def _session():
    from sqlalchemy.orm import Session
    from db_pg import get_engine
    return Session(get_engine())


def claim_submission(key: str) -> bool:
    """True for the first request with this key, False for any repeat."""
    from sqlalchemy.exc import IntegrityError
    from models_pg import SubmissionKey
    try:
        with _session() as s, s.begin():
            s.add(SubmissionKey(key=key))
        return True
    except IntegrityError:
        return False


def finish_submission(key: str, result: str) -> None:
    from sqlalchemy import update
    from models_pg import SubmissionKey
    if not key:
        return
    with _session() as s, s.begin():
        s.execute(update(SubmissionKey).where(SubmissionKey.key == key).values(result=str(result)[:128]))


def release_submission(key: str) -> None:
    """The first request failed: let the form be sent again."""
    from sqlalchemy import delete
    from models_pg import SubmissionKey
    if not key:
        return
    try:
        with _session() as s, s.begin():
            s.execute(delete(SubmissionKey).where(SubmissionKey.key == key, SubmissionKey.result.is_(None)))
    except Exception:
        logger.exception("Could not release a submission key")


def submission_result(key: str):
    """The first request's result, or None while it's still running."""
    from models_pg import SubmissionKey
    with _session() as s:
        row = s.get(SubmissionKey, key)
        return row.result if row else None


def purge_old() -> int:
    from sqlalchemy import delete
    from models_pg import SubmissionKey
    cutoff = datetime.datetime.now(datetime.timezone.utc) - KEEP
    with _session() as s, s.begin():
        return s.execute(delete(SubmissionKey).where(SubmissionKey.created_at <= cutoff)).rowcount or 0
