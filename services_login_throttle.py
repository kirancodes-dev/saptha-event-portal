"""
services_login_throttle.py — throttle failed logins and password-reset
requests per IP and per account (BLK-13).

At most LOGIN_THROTTLE_IP_LIMIT attempts per IP and LOGIN_THROTTLE_ACCOUNT_LIMIT
per account in any LOGIN_THROTTLE_WINDOW seconds (a sliding window), and at
most LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT failed logins per account in any hour,
so a slow guesser can't stay just under the per-minute limit (UPG-37). Counters
live in Redis when REDIS_URL is set, otherwise in the ``login_attempts`` table,
so every instance and gunicorn worker sees the same numbers.

  * Callers check ``retry_after`` before looking at credentials, so the answer
    is the same whether or not the account exists.
  * Only failures are recorded (every request, for password resets); a refused
    attempt isn't, so a lockout ends one window after the attempts that caused it.
  * A successful login clears that account's counter, never the IP's: one valid
    account mustn't buy more guesses at others.
  * Keys are hashed, so neither emails nor IPs are stored.
"""
import hashlib
import logging
import math
import secrets
import time
from contextlib import contextmanager

from flask import current_app

logger = logging.getLogger(__name__)

LOGIN = 'login'   # web and API login share one counter
RESET = 'reset'   # password-reset requests

REDIS_PREFIX = 'login-throttle:'
HOUR = 3600


def _now():
    return time.time()


def _settings():
    cfg = current_app.config
    return (int(cfg.get('LOGIN_THROTTLE_IP_LIMIT', 5)),
            int(cfg.get('LOGIN_THROTTLE_ACCOUNT_LIMIT', 5)),
            int(cfg.get('LOGIN_THROTTLE_WINDOW', 60)),
            int(cfg.get('LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT', 20)))


def _keep_for():
    """How long recorded attempts are needed: the longest window."""
    return max(_settings()[2], HOUR)


def _key(scope, kind, value):
    return hashlib.sha256(f'{scope}:{kind}:{value}'.encode()).hexdigest()


def _counters(scope, ip, email):
    """(key, limit, window) for each count this attempt is checked against.
    The account key is counted twice: per minute and, for logins, per hour."""
    ip_limit, account_limit, window, hourly_limit = _settings()
    counters = []
    if ip:
        counters.append((_key(scope, 'ip', ip), ip_limit, window))
    email = (email or '').strip().lower()
    if email:
        account = _key(scope, 'account', email)
        counters.append((account, account_limit, window))
        if scope == LOGIN:
            counters.append((account, hourly_limit, HOUR))
    return counters


def _wait(times, limit, now, window):
    """Seconds until fewer than ``limit`` of ``times`` (sorted) are in the window."""
    times = [t for t in times if t > now - window]
    if len(times) < limit:
        return 0
    return max(1, math.ceil(times[len(times) - limit] + window - now))


# ── Storage ────────────────────────────────────────────────────────────────

_redis_clients = {}


def _redis_client():
    import os

    import redis
    url = os.environ.get('REDIS_URL', '')
    if url not in _redis_clients:
        _redis_clients[url] = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    return _redis_clients[url]


def _use_redis():
    return current_app.config.get('LOGIN_THROTTLE_STORAGE') == 'redis'


@contextmanager
def _primary():
    """A transaction on the primary engine (attempts are recorded on POSTs,
    but the check must never read a lagging replica)."""
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    with Session(get_engine()) as s:
        with s.begin():
            yield s


def _times(key, now, window):
    if _use_redis():
        try:
            return [score for _, score in _redis_client().zrangebyscore(
                REDIS_PREFIX + key, now - window, '+inf', withscores=True)]
        except Exception as exc:
            logger.warning("Login throttle: Redis unavailable (%s); using the database", exc)
    from models_pg import LoginAttempt
    with _primary() as s:
        rows = (s.query(LoginAttempt.at)
                .filter(LoginAttempt.key == key, LoginAttempt.at > now - window)
                .order_by(LoginAttempt.at).all())
    return [r.at for r in rows]


def _add(keys, now, keep_for):
    if _use_redis():
        try:
            pipe = _redis_client().pipeline()
            for key in keys:
                pipe.zadd(REDIS_PREFIX + key, {f'{now}:{secrets.token_hex(4)}': now})
                pipe.zremrangebyscore(REDIS_PREFIX + key, '-inf', now - keep_for)
                pipe.expire(REDIS_PREFIX + key, keep_for + 1)
            pipe.execute()
            return
        except Exception as exc:
            logger.warning("Login throttle: Redis unavailable (%s); using the database", exc)
    from models_pg import LoginAttempt
    with _primary() as s:
        s.query(LoginAttempt).filter(LoginAttempt.at <= now - keep_for).delete()
        s.add_all([LoginAttempt(key=key, at=now) for key in keys])


def _clear(key):
    if _use_redis():
        try:
            _redis_client().delete(REDIS_PREFIX + key)
            return
        except Exception as exc:
            logger.warning("Login throttle: Redis unavailable (%s); using the database", exc)
    from models_pg import LoginAttempt
    with _primary() as s:
        s.query(LoginAttempt).filter(LoginAttempt.key == key).delete()


# ── API ────────────────────────────────────────────────────────────────────

def retry_after(scope, ip, email=''):
    """Seconds the caller must wait before another attempt; 0 if allowed.
    Fails open (0) if the counters can't be read, after logging why."""
    now = _now()
    try:
        return max([_wait(_times(key, now, window), limit, now, window)
                    for key, limit, window in _counters(scope, ip, email)] or [0])
    except Exception:
        logger.exception("Login throttle check failed; allowing the attempt")
        return 0


def record_failure(scope, ip, email=''):
    """Count one failed attempt (or one reset request) against the IP and account."""
    keys = list(dict.fromkeys(key for key, _, _ in _counters(scope, ip, email)))
    if not keys:
        return
    try:
        _add(keys, _now(), _keep_for())
    except Exception:
        logger.exception("Login throttle: could not record an attempt")


def clear_account(scope, email):
    """A successful login: forget that account's failures, per minute and per
    hour (the IP's stay)."""
    email = (email or '').strip().lower()
    if not email:
        return
    try:
        _clear(_key(scope, 'account', email))
    except Exception:
        logger.exception("Login throttle: could not clear an account")


def message(seconds):
    return f"Too many attempts. Please try again in {seconds} seconds."


def purge_expired():
    """Delete database rows older than the longest window; returns how many were
    removed. (Redis keys expire on their own.)"""
    from models_pg import LoginAttempt
    with _primary() as s:
        return s.query(LoginAttempt).filter(LoginAttempt.at <= _now() - _keep_for()).delete()


def reset_all():
    """Forget every counter (tests)."""
    from models_pg import LoginAttempt
    with _primary() as s:
        s.query(LoginAttempt).delete()
    if _use_redis():
        try:
            client = _redis_client()
            for key in client.scan_iter(match=REDIS_PREFIX + '*'):
                client.delete(key)
        except Exception as exc:
            logger.warning("Login throttle: Redis unavailable (%s)", exc)
