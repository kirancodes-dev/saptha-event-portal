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

A paid plan (UPG-255) counts per month: EMAIL_MONTHLY_LIMIT (0, the default,
means none) caps the main account's emails in a UTC month, beside the daily
limit, kept under ``YYYY-MM``. With Brevo as the main sender, Gmail SMTP
(MAIL_USER and MAIL_PASS) sends what Brevo can't, counted as the ``smtp``
account under ``YYYYMMDD-g`` against EMAIL_SMTP_DAILY_LIMIT (default 450,
for Gmail's 500 a day).
"""
import datetime
import logging
from contextlib import contextmanager

from flask import current_app

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 450
BACKUP = 'backup'
DEFAULT_BACKUP_LIMIT = 270
SMTP = 'smtp'
_SETTING = {'main': ('EMAIL_DAILY_LIMIT', DEFAULT_LIMIT), BACKUP: ('EMAIL_BACKUP_DAILY_LIMIT', DEFAULT_BACKUP_LIMIT),
            SMTP: ('EMAIL_SMTP_DAILY_LIMIT', DEFAULT_LIMIT)}
MONTHLY = 'EMAIL_MONTHLY_LIMIT'


class _Refused(Exception):
    """The month is full: undo the day's place taken in the same transaction."""


def smtp_fallback_configured() -> bool:
    """Brevo is the main sender and Gmail SMTP is set to send what it can't (UPG-255)."""
    import os
    return bool(os.environ.get('BREVO_API_KEY', '').strip() and os.environ.get('MAIL_USER', '').strip()
                and os.environ.get('MAIL_PASS', '').strip())


def backup_configured() -> bool:
    """Is a backup Brevo account set (UPG-224)?"""
    import os
    return bool(os.environ.get('BREVO_BACKUP_API_KEY', '').strip())


def limit(account: str = 'main') -> int:
    key, default = _SETTING[account]
    return _setting(key, default)


def monthly_limit() -> int:
    """The main account's emails a UTC month; 0 = none (UPG-255)."""
    return _setting(MONTHLY, 0)


def _setting(key: str, default: int) -> int:
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


def month() -> str:
    return today()[:7]


def _key(account: str) -> str:
    """The table row for today's count: the date, YYYYMMDD-b for the backup,
    YYYYMMDD-g for Gmail SMTP behind Brevo."""
    day = today()
    if account == 'main':
        return day
    return day.replace('-', '') + ('-b' if account == BACKUP else '-g')


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


def sent_this_month() -> int:
    """The main account's emails this UTC month (counted while a monthly limit is set)."""
    from models_pg import EmailQuota
    try:
        with _primary() as s:
            row = s.get(EmailQuota, month())
            return int(row.sent) if row else 0
    except Exception:
        logger.exception("Email quota: could not read this month's count")
        return 0


def _room(n: int, account: str) -> bool:
    cap = limit(account)
    if cap and sent_today(account) + n > cap:
        return False
    monthly = monthly_limit() if account == 'main' else 0
    return not monthly or sent_this_month() + n <= monthly


def available(n: int = 1) -> bool:
    """True when n more emails fit under today's limit, the backup account's included."""
    return (_room(n, 'main') or (smtp_fallback_configured() and _room(n, SMTP))
            or (backup_configured() and _room(n, BACKUP)))


def _take(s, key: str, n: int, cap: int) -> bool:
    from sqlalchemy import update

    from models_pg import EmailQuota
    dialect = s.get_bind().dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    s.execute(insert(EmailQuota).values(day=key, sent=0).on_conflict_do_nothing(index_elements=['day']))
    return bool(s.execute(update(EmailQuota).where(EmailQuota.day == key, EmailQuota.sent + n <= cap)
                          .values(sent=EmailQuota.sent + n)).rowcount)


def reserve(n: int = 1, account: str = 'main') -> bool:
    """Take n of today's places (and this month's, for the main account with a
    monthly limit); False (and nothing taken) if that passes a limit."""
    cap = limit(account)
    monthly = monthly_limit() if account == 'main' else 0
    if (not cap and not monthly) or n <= 0:
        return True
    which = 'day'
    try:
        with _primary() as s:
            if cap and not _take(s, _key(account), n, cap):
                taken = False
            elif monthly and not _take(s, month(), n, monthly):
                which = 'month'
                raise _Refused()
            else:
                taken = True
    except _Refused:
        taken = False                       # the transaction rolled the day's place back
    except Exception:
        logger.exception("Email quota: could not count an email; sending it anyway")
        return True
    if not taken:
        logger.warning("Email quota: the %s's limit of %s emails is reached on the %s account; "
                       "not sending to %s recipient(s) through it",
                       which, cap if which == 'day' else monthly, account, n)
    return taken


def release(n: int = 1, account: str = 'main') -> None:
    """The provider didn't accept the email: give its places back."""
    keys = ([_key(account)] if limit(account) else []) + ([month()] if account == 'main' and monthly_limit() else [])
    if not keys or n <= 0:
        return
    from sqlalchemy import update

    from models_pg import EmailQuota
    try:
        with _primary() as s:
            for key in keys:
                s.execute(update(EmailQuota).where(EmailQuota.day == key, EmailQuota.sent >= n)
                          .values(sent=EmailQuota.sent - n))
    except Exception:
        logger.exception("Email quota: could not give back an unsent email's place")
