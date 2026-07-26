"""
gunicorn.conf.py — Production Gunicorn configuration for SapthaEvent
=====================================================================
Multi-worker, stateless web fleet.

APScheduler has been removed from the web process — all scheduled and
async work now runs in the celery-worker / celery-beat containers.
This means we can safely run multiple Gunicorn workers without duplicate
job execution.

Tuned for:
  - 3-5 web replicas behind Nginx (docker-compose scale)
  - Each replica: 2-4 workers × N threads
  - 512 MB RAM per replica (Railway / Cloud Run tier)
  - Redis-backed sessions (no shared filesystem needed)
"""

import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────
# Rule of thumb: 2 × CPU + 1 per replica.
# Each replica in docker-compose gets its own CPU slice.
# Cap at 4 to avoid OOM on 512 MB instances.
_cpu  = multiprocessing.cpu_count()
workers = min((_cpu * 2) + 1, 4)

# Threads give concurrency within each worker for I/O-bound requests.
# Most of our I/O (email, Firestore) is now offloaded to Celery,
# so requests complete quickly — threads reduce latency spikes.
threads = 2

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
