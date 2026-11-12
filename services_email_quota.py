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

A backup Brevo account (UPG-224), set by BREVO_BACKUP_API_KEY, has its own
count and limit (EMAIL_BACKUP_DAILY_LIMIT, default 270 for Brevo's free 300 a
day), kept in the same table under ``YYYYMMDD-b`` so no migration is needed.
Every function takes ``account='main'`` or ``'backup'``; ``available()`` is
True while either account has room.
"""
import datetime
import logging
from contextlib import contextmanager

from flask import current_app

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 450
BACKUP = 'backup'
DEFAULT_BACKUP_LIMIT = 270
_SETTING = {'main': ('EMAIL_DAILY_LIMIT', DEFAULT_LIMIT), BACKUP: ('EMAIL_BACKUP_DAILY_LIMIT', DEFAULT_BACKUP_LIMIT)}


def backup_configured() -> bool:
    """Is a backup Brevo account set (UPG-224)?"""
    import os
    return bool(os.environ.get('BREVO_BACKUP_API_KEY', '').strip())


def limit(account: str = 'main') -> int:
    key, default = _SETTING[account]
    try:
        value = current_app.config.get(key, default)
    except RuntimeError:   # outside an app context
        import os
        value = os.environ.get(key, default)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def _key(account: str) -> str:
    """The table row for today's count: the date, or YYYYMMDD-b for the backup."""
    day = today()
    return day if account == 'main' else day.replace('-', '') + '-b'


@contextmanager
def _primary():
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    with Session(get_engine()) as s:
        with s.begin():
            yield s


def sent_today(account: str = 'main') -> int:
    from models_pg import EmailQuota
    try:
        with _primary() as s:
            row = s.get(EmailQuota, _key(account))
            return int(row.sent) if row else 0
    except Exception:
        logger.exception("Email quota: could not read today's count")
        return 0


def _room(n: int, account: str) -> bool:
    cap = limit(account)
    return not cap or sent_today(account) + n <= cap


def available(n: int = 1) -> bool:
    """True when n more emails fit under today's limit, the backup account's included."""
    return _room(n, 'main') or (backup_configured() and _room(n, BACKUP))


def reserve(n: int = 1, account: str = 'main') -> bool:
    """Take n of today's places; False (and nothing taken) if that passes the limit."""
    cap = limit(account)
    if not cap or n <= 0:
        return True
    from sqlalchemy import update

    from models_pg import EmailQuota
    day = _key(account)
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
        logger.warning("Email quota: today's limit of %s emails is reached on the %s account; "
                       "not sending to %s recipient(s) through it", cap, account, n)
    return bool(taken)


def release(n: int = 1, account: str = 'main') -> None:
    """The provider didn't accept the email: give its places back."""
    if not limit(account) or n <= 0:
        return
    from sqlalchemy import update

    from models_pg import EmailQuota
    try:
        with _primary() as s:
            s.execute(update(EmailQuota).where(EmailQuota.day == _key(account), EmailQuota.sent >= n)
                      .values(sent=EmailQuota.sent - n))
    except Exception:
        logger.exception("Email quota: could not give back an unsent email's place")
