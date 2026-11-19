"""
gunicorn.conf.py — Production Gunicorn configuration for SapthaEvent
=====================================================================
One process with several threads per copy, sized to the database's
connection slots (UPG-319; docs/DEPLOY.md, "Traffic and database
connections"). WEB_CONCURRENCY sets the processes, GUNICORN_THREADS the
threads in each.

APScheduler is not in the web process; scheduled work comes in through the
/cron endpoints, so several processes never run a job twice.
"""

import os

# One process with several threads per Cloud Run copy (UPG-319): the copies
# share one small database pool per process, so fewer processes means fewer
# database connections for the same number of requests at once. Requests
# mostly wait on the database and mail, which threads overlap. Cloud Run's
# --concurrency should equal workers × threads, so it starts another copy
# instead of queueing more requests than this one can work on.
workers = int(os.environ.get('WEB_CONCURRENCY', os.environ.get('WORKERS', '1')))
threads = int(os.environ.get('GUNICORN_THREADS', '8'))

# Use gevent event loop if available (install greenlet + gevent for it).
# Falls back to sync worker class automatically.
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'sync')

# ── Server ────────────────────────────────────────────────
bind           = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
timeout        = 60          # reduced from 120s — Celery handles slow ops now
keepalive      = 5
graceful_timeout = 30

# ── Memory leak guard ─────────────────────────────────────
max_requests        = 1000
max_requests_jitter = 200    # spread restarts to avoid all-at-once

# ── Logging ───────────────────────────────────────────────
accesslog  = '-'
errorlog   = '-'
loglevel   = os.environ.get('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sus'


# The access log must not record the token in a set-password, reset or
# cancel link (UPG-152): the request line, path and query are redacted.
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # for log_redact
try:
    from gunicorn.glogging import Logger as _GunicornLogger

    from log_redact import redact as _redact

    class RedactingLogger(_GunicornLogger):
        def atoms(self, resp, req, environ, request_time):
            atoms = super().atoms(resp, req, environ, request_time)
            for key in ('r', 'U', 'q'):
                if key in atoms:
                    atoms[key] = _redact(atoms[key])
            return atoms

    logger_class = RedactingLogger
except ImportError:      # gunicorn not installed (tests, local tools)
    pass

# ── Process title ─────────────────────────────────────────
proc_name = 'sapthaevent-web'

# ── Hooks ─────────────────────────────────────────────────
def on_starting(server):
    server.log.info("SapthaEvent web fleet starting — workers=%d threads=%d", workers, threads)

def post_fork(server, worker):
    """Called after each worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_exit(server, worker):
    server.log.info("Worker exiting (pid: %s)", worker.pid)
