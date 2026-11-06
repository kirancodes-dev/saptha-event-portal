"""
services_email_quota.py — a daily email limit under the provider's free quota (UPG-152).

Every email the app sends counts, one per recipient, against EMAIL_DAILY_LIMIT
(default 450, for a provider that allows 500 a day; 0 means no limit). The
count is kept per UTC day in the ``email_quota`` table, so every instance and
worker shares it.

  * ``reserve(n)`` takes n places atomically and is False once the day's limit
    would be passed: utils_email._send then sends nothing.
  * ``release(n)`` gives places back when the provider refused the email.
  * ``available()`` is the check pages make first, so they can show the
    organizer-contact message instead of promising an email.

If the table can't be reached the email is sent anyway (fail open), after
logging why: a broken counter must not stop registrations.
"""
import datetime
import logging
from contextlib import contextmanager

from flask import current_app

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 450


def limit() -> int:
    try:
        value = current_app.config.get('EMAIL_DAILY_LIMIT', DEFAULT_LIMIT)
    except RuntimeError:   # outside an app context
        import os
        value = os.environ.get('EMAIL_DAILY_LIMIT', DEFAULT_LIMIT)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


@contextmanager
def _primary():
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    with Session(get_engine()) as s:
        with s.begin():
            yield s


def sent_today() -> int:
    from models_pg import EmailQuota
    try:
        with _primary() as s:
            row = s.get(EmailQuota, today())
            return int(row.sent) if row else 0
    except Exception:
        logger.exception("Email quota: could not read today's count")
        return 0


def available(n: int = 1) -> bool:
    """True when n more emails fit under today's limit."""
    cap = limit()
    return not cap or sent_today() + n <= cap


def reserve(n: int = 1) -> bool:
    """Take n of today's places; False (and nothing taken) if that passes the limit."""
    cap = limit()
    if not cap or n <= 0:
        return True
    from sqlalchemy import update

    from models_pg import EmailQuota
    day = today()
    try:
        with _primary() as s:
            dialect = s.get_bind().dialect.name
            if dialect == 'postgresql':
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            s.execute(insert(EmailQuota).values(day=day, sent=0).on_conflict_do_nothing(index_elements=['day']))
            taken = s.execute(update(EmailQuota)
                              .where(EmailQuota.day == day, EmailQuota.sent + n <= cap)
                              .values(sent=EmailQuota.sent + n)).rowcount
    except Exception:
        logger.exception("Email quota: could not count an email; sending it anyway")
        return True
    if not taken:
        logger.warning("Email quota: today's limit of %s emails is reached; not sending to %s recipient(s)", cap, n)
    return bool(taken)


def release(n: int = 1) -> None:
    """The provider didn't accept the email: give its places back."""
    if not limit() or n <= 0:
        return
    from sqlalchemy import update

    from models_pg import EmailQuota
    try:
        with _primary() as s:
            s.execute(update(EmailQuota).where(EmailQuota.day == today(), EmailQuota.sent >= n)
                      .values(sent=EmailQuota.sent - n))
    except Exception:
        logger.exception("Email quota: could not give back an unsent email's place")
