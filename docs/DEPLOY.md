# Deploying SapthaEvent

This guide is being written section by section. The full Cloud Run + Supabase
guide (every setting, first Super Admin, rollback, backups, monitoring) comes
with UPG-32 in `docs/FEATURE_REVIEW.md`. Until then,
`docs/DEPLOYMENT.md` covers the container and environment basics.

## Database migrations

The schema is built and changed only by Alembic migrations (`migrations/versions/`).
In production (`FLASK_ENV=production`) the app never creates or alters tables at
start-up: it checks that the database is at the newest migration and refuses to
start otherwise, with a message saying what to run. In development, start-up still
creates missing tables and columns so a local SQLite file just works.

Run migrations **before** the new revision serves traffic, once per deploy, from
the same image (so the migration files match the code):

```bash
# Cloud Run: a job that runs the image's alembic once, then deploy the service
gcloud run jobs create saptha-migrate --image "$IMAGE" --region "$REGION" \
  --set-secrets DATABASE_URL=DATABASE_URL:latest --command alembic --args upgrade,head
gcloud run jobs execute saptha-migrate --region "$REGION" --wait
gcloud run deploy saptha --image "$IMAGE" --region "$REGION"
```

```bash
# Anywhere else (DATABASE_URL set in the environment)
alembic upgrade head
```

Don't run migrations from every container's start command: several instances
starting together would race.

**A new, empty database:** `alembic upgrade head` builds every table.

**A database created before migrations existed** (by the old start-up
`create_all`/`ALTER TABLE`): bring it to the current models once with a
development start-up of this version (which adds any missing columns), then
record it as migrated without running anything:

```bash
alembic stamp 0001_baseline
```

**Checking:** `alembic current` shows the database's revision and `alembic heads`
the code's. **Rolling back** a migration: `alembic downgrade -1` (only before the
new revision has written data the old schema can't hold).

**Adding a change:** edit `models_pg.py`, then
`alembic revision --autogenerate -m "what changed"` against a database at head,
read the generated file, and commit it with the code.

## Scheduled jobs

Reminders, event lifecycle changes and clean-up run on a schedule.

- **Self-hosted with `docker-compose.yml`:** the `celery-beat` and
  `celery-worker` services run them (schedule in `celery_app.py`). Nothing
  else to set up.
- **A single web service (Cloud Run, or any host without Celery beat):** an
  outside scheduler calls the app. Set this up once, with **one** scheduler:
  Cloud Scheduler (below) or the GitHub Actions workflow. Calling from both is
  harmless but wasteful.

### The endpoint

`POST https://<BASE_URL>/internal/cron/<job>` with the header
`X-Cron-Secret: <CRON_SECRET>`.

| Job | Suggested schedule | What it does |
|---|---|---|
| `reminders` | every hour | Day-before ticket email and WhatsApp reminder, coordinators' briefing, and the 3-day reminder. Each registration is reminded once (`ticket_sent`, `early_reminder_sent`). |
| `lifecycle` | every 6 hours | Closes registration after the deadline, and marks events whose end date has passed as `completed`. It never deletes anything. Each change is in the workflow audit trail. |
| `cleanup` | daily | Deletes expired sessions, login attempts older than the throttle window (one hour), and outbox rows sent more than 7 days ago or failed more than 30 days ago. Nothing else. |
| `outbox` | every 15 minutes | Retries background tasks (emails, WhatsApp, notices) that failed or timed out inline; see "Background tasks" below. |

Answers: `200` with a JSON summary; `403` for a missing or wrong secret;
`503` when `CRON_SECRET` isn't set on the app; `404` for an unknown job;
`500` if the job failed (details in the app's log). Every job is safe to
repeat, so a retry after a failure or a timeout does no harm.

Without a Celery broker, the reminder emails go out inside the request (each
under `TASK_INLINE_TIMEOUT`), so a large event can take minutes. Give the scheduler a long deadline (below) and
the Cloud Run service a request timeout to match (`--timeout=1800`).
Registrations already reminded are skipped, so a run that times out
continues where it stopped at the next hour.

### 1. Make the secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it as `CRON_SECRET` on the app (on Cloud Run, as a Secret Manager secret):

```bash
printf '%s' '<the value>' | gcloud secrets create cron-secret --data-file=-
gcloud run services update saptha-event --region=asia-south1 \
  --update-secrets=CRON_SECRET=cron-secret:latest --timeout=1800
```

### 2a. Cloud Scheduler (recommended on Cloud Run)

```bash
APP=https://events.example.edu        # the app's BASE_URL
REGION=asia-south1
SECRET='<the value>'

gcloud scheduler jobs create http saptha-reminders --location=$REGION \
  --schedule='0 * * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/reminders" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=30m

gcloud scheduler jobs create http saptha-lifecycle --location=$REGION \
  --schedule='15 */6 * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/lifecycle" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=10m

gcloud scheduler jobs create http saptha-cleanup --location=$REGION \
  --schedule='15 3 * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/cleanup" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=5m

gcloud scheduler jobs create http saptha-outbox --location=$REGION \
  --schedule='*/15 * * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/outbox" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=15m
```

Check one by running it now and reading its last result:

```bash
gcloud scheduler jobs run saptha-cleanup --location=$REGION
gcloud scheduler jobs describe saptha-cleanup --location=$REGION --format='value(status)'
```

To change the secret: update the Secret Manager value and redeploy, then
`gcloud scheduler jobs update http <job> --update-headers="X-Cron-Secret=<new value>"`
for each of the four jobs.

### 2b. GitHub Actions (any host)

`.github/workflows/cron.yml` calls the same four jobs on the same schedule.
In the repository's **Settings → Secrets and variables → Actions**, add:

- `CRON_URL`: the app's `BASE_URL`, for example `https://events.example.edu`;
- `CRON_SECRET`: the same value as the app's `CRON_SECRET`.

Until both are set, the workflow does nothing. Run a job by hand from the
**Actions** tab (*Scheduled jobs → Run workflow*). GitHub may start scheduled
runs several minutes late, and pauses schedules in repositories with no
activity for 60 days.

### Not covered by the endpoint

The SPOC's registration-velocity alert and the daily analytics roll-up still
run only under Celery beat.

## Background tasks

Emails, WhatsApp messages, notices and certificate runs are Celery tasks. They
run in one of two modes.

**Inline + outbox (no broker; the default on a single Cloud Run service).**
When `CELERY_BROKER_URL` isn't a `redis://` URL, each task runs inside the
request that queued it, once, in a worker thread, for at most
`TASK_INLINE_TIMEOUT` seconds (default 10). The request never waits longer and
never fails because of a task. A task that raises or runs past the limit is
written to the `outbox` table (one row per distinct send: its key is a hash of
the task and its arguments). The `outbox` cron job (above) retries due rows:
5 minutes after the first failure, doubling up to 6 hours, until it succeeds
or has failed `OUTBOX_MAX_ATTEMPTS` times (default 5), when the row is marked
`failed` and logged as an error. Each row is claimed with a conditional
update, so two cron runs never send it twice; a task that timed out but then
finished is marked sent and not retried. `TASK_INLINE_THREADS` (default 8)
caps how many tasks run at once per instance. On Cloud Run, a task still
running after its request has answered gets little CPU; leave the default
timeout, or use "CPU always allocated" if certificate runs for large events
time out.

To see what's waiting: `SELECT task_name, status, attempts, next_attempt_at,
last_error FROM outbox WHERE status <> 'done' ORDER BY next_attempt_at;`.

**Broker mode (self-hosted with `docker-compose.yml`).** With
`CELERY_BROKER_URL=redis://…`, tasks are queued to the Celery worker, which
retries them itself (each task's `max_retries`); the outbox isn't used and the
`outbox` job finds nothing to do.

