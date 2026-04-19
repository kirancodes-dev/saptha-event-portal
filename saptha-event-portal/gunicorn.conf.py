"""
gunicorn.conf.py  —  Production Gunicorn Configuration for SapthaEvent
=======================================================================
Railway runs:  gunicorn -c gunicorn.conf.py app:app

Tuned for:
  - 2000 concurrent users
  - Railway free tier (512 MB RAM, 1 vCPU)
  - Flask-Limiter in-memory (or Redis if REDIS_URL set)
  - APScheduler background thread (only 1 worker to avoid double scheduling)
"""
import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────
# Use 1 worker + multiple threads.
# Multiple workers would start APScheduler N times (duplicate reminders).
# Threads share the same process → scheduler runs exactly once.
workers = 1
threads = multiprocessing.cpu_count() * 2 + 1   # 3 on 1-core Railway

# ── Server ────────────────────────────────────────────────
bind    = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
timeout = 120          # 2 min — gives email + Firestore ops room to complete
keepalive = 5

# ── Logging ───────────────────────────────────────────────
accesslog  = '-'       # stdout → Railway log stream
errorlog   = '-'
loglevel   = 'info'
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sus'

# ── Process title (visible in Railway metrics) ────────────
proc_name = 'sapthaevent'

# ── Graceful restart ──────────────────────────────────────
graceful_timeout = 30
max_requests     = 1000   # restart workers after N requests (memory leak guard)
max_requests_jitter = 100