# Deploying SapthaEvent

How to run SapthaEvent in production on Google Cloud (Cloud Run for the app,
Cloud SQL PostgreSQL 16 for the data, Secret Manager for secrets, Cloud Storage
for uploads, Cloud Scheduler for timed jobs), the way the test deployment of
2026-10-17 was built. The same image runs anywhere with Docker and a
PostgreSQL database (Supabase works; set `DATABASE_URL`). `docs/DEPLOYMENT.md`
has the container basics. The go-live checklist at the end lists what only the
owner can do.

Contents: Google Cloud set-up · Settings · Database migrations · First Super
Admin · Uploads · Certificates · WhatsApp · Scheduled jobs · Background tasks · Backups ·
Restore drill · Rollback · Monitoring · Android app · Release check · Go-live
checklist.

## Google Cloud set-up

Values used below (change them to yours): project `saptha-event-261017`,
region `asia-south1` (Mumbai), service `saptha`, database instance `saptha-db`.

```bash
PROJECT=saptha-event-261017; REGION=asia-south1
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com
```

**1. The database.** A small instance is enough to start (the test used
`db-f1-micro`, 10 GB, daily backups). The app reaches it through the Cloud SQL
connector (`CLOUD_SQL_INSTANCE`), so the instance needs no public IP allow-list.

```bash
gcloud sql instances create saptha-db --database-version=POSTGRES_16 --region="$REGION" \
  --tier=db-f1-micro --storage-size=10 --backup-start-time=20:30
gcloud sql databases create saptha --instance=saptha-db
gcloud sql users create saptha --instance=saptha-db --password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

**2. Secrets.** Put every secret in Secret Manager (never in the image or in
git): one `gcloud secrets create NAME --data-file=-` per setting, fed from
`printf '%s' '<value>'`. The settings and how to make each value are in the next
section.

**3. Build and deploy.**

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT/saptha/web:$(git rev-parse --short HEAD)"
gcloud artifacts repositories create saptha --repository-format=docker --location="$REGION"   # once
gcloud builds submit --tag "$IMAGE"
# Migrations first (next section), then the service:
gcloud run deploy saptha --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --min-instances=0 --max-instances=3 --memory=1Gi --timeout=1800 \
  --add-cloudsql-instances="$PROJECT:$REGION:saptha-db" \
  --set-env-vars=FLASK_ENV=production,CLOUD_SQL_INSTANCE=$PROJECT:$REGION:saptha-db,DB_USER=saptha,DB_NAME=saptha,BASE_URL=https://<your-service-url>,WEB_CONCURRENCY=2 \
  --set-secrets=SECRET_KEY=SECRET_KEY:latest,MASTER_SECRET_KEY=MASTER_SECRET_KEY:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,DB_PASS=DB_PASS:latest,CRON_SECRET=CRON_SECRET:latest,BREVO_API_KEY=BREVO_API_KEY:latest
```

Add the Razorpay, mail sender, storage and optional settings the same way. The
first deploy prints the service URL; set `BASE_URL` to it (or to the university
domain once it points there) and deploy again. The service account Cloud Run
uses needs **Cloud SQL Client**, **Secret Manager Secret Accessor** and, for
uploads, **Storage Object Admin** on the bucket.

## Settings

`.env.example` lists every setting the app reads, grouped, with what each is for
and how to generate or find its value (a test keeps it complete:
`tests/test_production_boot.py`). In production the app checks the important
ones at start-up and refuses to start, naming **every** problem at once, if any
is missing or weak (UPG-20):

| Setting | What to put there |
|---|---|
| `FLASK_ENV` | `production` (turns the checks on) |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Two different random values, 32+ characters: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `MASTER_SECRET_KEY` | A random value, 12+ characters; Super Admin logins must type it |
| `BASE_URL` | The public `https://` address; every emailed, QR and WhatsApp link is built from it |
| `DATABASE_URL` or `CLOUD_SQL_INSTANCE` (+ `DB_USER`, `DB_PASS`, `DB_NAME`) | PostgreSQL; the schema must be at the newest migration |
| `BREVO_API_KEY` (or `RESEND_API_KEY`, or `MAIL_USER` + `MAIL_PASS`) and `MAIL_FROM` | A mail provider and a sender it has verified; accounts are opened through emailed links |
| `CRON_SECRET` | A random value, 24+ characters, shared with Cloud Scheduler |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | All three or none (none: paid events refuse online payment) |
| `PAYMENT_SIMULATION` | Never set in production |
| `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASS` | Optional: the first Super Admin (12+ character password) |

Also set: `SUPPORT_EMAIL` (shown on the privacy, terms and payment-failed pages),
`LOGIN_THROTTLE_IP_LIMIT=50` (many students share one campus IP),
`SENTRY_DSN` (error reports), `STORAGE_TYPE=gcs` and `GCS_BUCKET_NAME` (uploads), the
certificate settings (see "Certificates"), and the optional features in
`.env.example` (all off by default).

**Daily email limit (UPG-152).** `EMAIL_DAILY_LIMIT` (default 450) caps the emails the
app sends in a UTC day, every kind and every instance together, one per recipient;
at the limit it sends nothing and tells people to contact the organizer. Set it below
your provider's quota: about 270 on Brevo's free plan (300 a day), 450 on Gmail
(500), 1,800 on Google Workspace (2,000). `NOTIFY_TEAM_MEMBERS=true` also emails every team
member (off: the lead only). `PARTICIPANT_RESET_LIMIT` (1) and
`PARTICIPANT_RESET_WINDOW_HOURS` (48) limit a registration account's reset emails.
`/diag/email` shows today's count. The limit's table comes from migration
`0010_email_quota`.

**Backup email account (UPG-224).** `BREVO_BACKUP_API_KEY` (a secret), the API key of a
second Brevo account, sends what the main account can't: once the main account reaches
`EMAIL_DAILY_LIMIT`, or when Brevo refuses an email (its own 300 a day used up). It has
its own `EMAIL_BACKUP_DAILY_LIMIT` (default 270) and sends from `MAIL_FROM_BACKUP`, else
`MAIL_FROM`: verify that sender in the second account too (Brevo → Senders). Together the
day's capacity is about 540. People are told to contact the organizer only when both are
full. `/diag/email?via=backup` sends a test through the backup alone and shows its count;
without the key nothing changes. No migration: the backup's count is a second row in
`email_quota`.

## Database migrations

The schema is built and changed only by Alembic migrations (`migrations/versions/`).
In production (`FLASK_ENV=production`) the app never creates or alters tables at
start-up: it checks that the database is at the newest migration and refuses to
start otherwise, with a message saying what to run. In development, start-up still
creates missing tables, columns and indexes so a local SQLite file just works.

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

**Migration `0007_one_active_registration`** adds the database rule that a person
holds at most one active (not cancelled or waitlisted) registration per event. If
an existing database already has someone registered twice for one event, the
upgrade stops before changing anything and lists each case (event, email). Cancel
the extra registrations from the Super Admin's registrations page (keep one each;
refund any extra payment from the payments page), then run `alembic upgrade head`
again. It never cancels or deletes a registration itself.

**Migration `0009_naac_roles`** adds the IQAC coordinator and department admin
roles to the role type (PostgreSQL). Run it before the new revision, as usual.

**Migration `0008_certificates`** adds the `certificates` table (one current
certificate per person, event and type, enforced by a unique index). It changes
no existing table. Certificates issued before it stay in the old
`verified_certificates` documents and keep verifying at their old addresses.

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

## First Super Admin

Either way works; use a 12+ character password from a password manager.

- **First login:** set `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASS` (as secrets),
  deploy, and log in at `/login` as Super Admin with exactly those values and
  the `MASTER_SECRET_KEY`. That login creates the account. Afterwards remove
  `SUPER_ADMIN_PASS` from the service (the account keeps its password).
- **From a terminal:** with `DATABASE_URL` pointing at the production database,
  `SUPER_ADMIN_EMAIL=you@university.edu SUPER_ADMIN_PASS='…' python init_superadmin.py --i-know-this-is-production`
  (`--reset` also replaces an existing password). The script refuses a
  production-looking database without that flag (BLK-10).

Then, as the Super Admin, open `/diag/email?to=<your address>` once: the test
message must arrive, not in spam, from `MAIL_FROM`.

## Uploads and private file links (Cloud Storage)

Set `STORAGE_TYPE=gcs` and `GCS_BUCKET_NAME` to a bucket with **fine-grained**
access control (not uniform bucket-level access): public files are made public
one by one, private ones stay private. Give the runtime service account
`roles/storage.objectAdmin` on the bucket.

Private files are shared through signed links. On Cloud Run the default
credentials have no private key, so the app signs through IAM's signBlob
(UPG-99); the runtime service account must be allowed to sign as itself:

```bash
SA=<project-number>-compute@developer.gserviceaccount.com
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="serviceAccount:$SA" --role=roles/iam.serviceAccountTokenCreator
```

## Certificates

Certificates are PDFs stored **privately** (in the bucket above, never under a
public URL, or in `PRIVATE_STORAGE_DIR` with local storage) with each file's
SHA-256 on its record. People download their own after signing in, or through
the emailed link, which is signed with `SECRET_KEY` and expires after
`CERT_LINK_DAYS` (default 30). Changing `SECRET_KEY` voids every emailed link
(people can still download from "My certificates").

| Setting | What to put there |
|---|---|
| `COLLEGE_NAME` | The college's name as printed on certificates and the verification page |
| `COLLEGE_LOGO_PATH` | A logo file under `static/` (default `static/img/email-logo.png`, drawn on a dark panel) |
| `CERT_PRIMARY_COLOR`, `CERT_ACCENT_COLOR` | Hex colours (default `#0c1240` and `#c9a020`) |
| `CERT_CHUNK_SIZE` | Certificates per background step (default 100) |
| `CERT_LINK_DAYS` | How long an emailed download link works (default 30) |
| `VERIFY_RATE_LIMIT` | Lookups per address on the verification pages (default `30 per minute`) |

Issuing runs in the background through the outbox: without a Redis broker it
runs inside the request for up to `TASK_INLINE_TIMEOUT` seconds and carries on
in a thread; if the instance stops first, the `outbox` cron job finishes it.
Each event needs at least one signatory with a signature (on the event's
certificate page) before anything is issued.

## WhatsApp

Off until you switch it on. Messages go only to people who ticked "Send me
updates about this event on WhatsApp" or turned it on in their profile, each
message once, and never more than the monthly cap the Super Admin sets
(`/whatsapp/settings`). Email always goes out as well.

1. **Choose a provider.** Meta's WhatsApp Cloud API (`WHATSAPP_PROVIDER=meta`):
   create a Meta Business account and an app with the WhatsApp product, add the
   college's phone number, and copy the permanent access token (`META_WA_TOKEN`),
   the phone number ID (`META_WA_PHONE_ID`) and the app secret
   (`META_WA_APP_SECRET`); choose any long random `META_WA_VERIFY_TOKEN`. Or
   Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`).
2. **Submit the templates for approval.** `config/whatsapp_templates.json` has
   the four messages (registration confirmed, event reminder, event changed,
   event cancelled). For each, create a template in WhatsApp Manager (Meta) or
   the Content Template Builder (Twilio) with the **same name**, category
   **Utility**, language **English**, and the body as written, keeping the
   numbered variables `{{1}}`, `{{2}}`… in order (the file's `variables` says
   what each is, for the sample values Meta asks for). Approval usually takes
   minutes to a day; a rejected template can be edited and resubmitted.
3. **Point the webhook at the app** so STOP replies are honoured:
   `https://<BASE_URL>/whatsapp/webhook` (Meta: callback URL, with the verify
   token, subscribed to `messages`; Twilio: "A message comes in" on the
   WhatsApp sender). Requests without a valid provider signature are refused.
4. **It's on once the provider's settings are in** (set `WHATSAPP_ENABLED=false`
   to pause it). Set the monthly cap on
   `/whatsapp/settings` (default `WHATSAPP_MONTHLY_CAP`, 1000). At the cap,
   WhatsApp pauses until the next month and the Super Admins get one email.

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
| `impact` | daily | Asks the organiser and a sample of attendees of each event that ended for a testimonial, once per event (UPG-145). |
| `naac` | daily | Emails each organiser whose post-event NAAC report is overdue, once a day until it's submitted (UPG-144). |
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
gcloud scheduler jobs create http saptha-impact --location=$REGION \
  --schedule='0 11 * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/impact" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=10m
gcloud scheduler jobs create http saptha-naac --location=$REGION \
  --schedule='0 10 * * *' --time-zone='Asia/Kolkata' \
  --uri="$APP/internal/cron/naac" --http-method=POST \
  --headers="X-Cron-Secret=$SECRET" --attempt-deadline=10m
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

## Backups

A dump of the whole database is taken every day and kept in a **private**
bucket. It holds every record of every person, so treat the bucket like the
database itself. Dumps are never committed: `.gitignore` refuses `*.dump`,
`*.sql`, `*.sql.gz` and `*.backup`.

**What runs:** `scripts/backup_db.sh` runs `pg_dump --format=custom` against
`DATABASE_URL`, checks the dump can be read, uploads it as
`saptha-<UTC date and time>.dump` to `BACKUP_BUCKET` (`s3://…` or `gs://…`),
and deletes dumps older than `BACKUP_RETENTION_DAYS` (default 30). The local
copy is deleted when it ends. `pg_dump` must be the database server's major
version or newer.

**Schedule (pick one):**

- **GitHub Actions** (`.github/workflows/backup.yml`, daily at 02:00 IST, or
  run it by hand from the Actions tab). Repository secrets:
  `BACKUP_DATABASE_URL` (a read-only database user is enough),
  `BACKUP_BUCKET`, and for S3 `BACKUP_AWS_ACCESS_KEY_ID`,
  `BACKUP_AWS_SECRET_ACCESS_KEY` and, for Supabase Storage or another
  S3-compatible service, `S3_ENDPOINT_URL`. Optional variables:
  `BACKUP_RETENTION_DAYS`, `BACKUP_AWS_REGION`, `BACKUP_PG_MAJOR` (default 17).
  It does nothing until the first two secrets are set.
- **Cloud Run job + Cloud Scheduler:** build a small image from
  `postgres:17` with the gcloud CLI and this script, run it as a job with
  `DATABASE_URL` from Secret Manager and `BACKUP_BUCKET=gs://<bucket>/backups`,
  and trigger the job daily from Cloud Scheduler. The job's service account
  needs only `roles/storage.objectAdmin` on that bucket.

**Bucket permissions:** no public access (S3 "Block all public access" on;
GCS "Public access prevention" enforced; a Supabase Storage bucket that is
not public). Only the backup identity can write, and only the people who run
restores can read. A lifecycle rule that deletes objects after the retention
period is a good second guard.

**Storage settings the app shares** (UPG-17, folded in here, D-5):
`STORAGE_TYPE=s3` with `AWS_*` and, for Supabase Storage,
`S3_ENDPOINT_URL=https://<project>.supabase.co/storage/v1/s3`. Exports are
uploaded as private objects and handed out through links that expire after
15 minutes. In production a storage error is an error: nothing is written to
the container's disk.

## Restore drill

Run this once before launch and then every term, so a restore is never done
for the first time in an emergency:

1. Create an **empty** database (a new Supabase project, or
   `createdb saptha_restore_test`). `scripts/restore_db.sh` refuses a target
   that already has tables.
2. `scripts/restore_db.sh s3://<bucket>/backups/saptha-<date>.dump "<target URL>"`
   (or `gs://…`, or a downloaded file). It prints the rows per table.
3. Check: `psql "<target URL>" -c "ANALYZE"` then compare row counts with the
   live database (`SELECT relname, n_live_tup FROM pg_stat_user_tables`), and
   `DATABASE_URL="<target URL>" alembic current` shows the expected revision.
4. To recover for real: point the app's `DATABASE_URL` at the restored
   database and redeploy (or restore into the original after renaming it).
   Data written after the dump's time is lost, so note the time in the
   incident record.
5. Delete the test database when the drill is done; it holds real personal data.

## Rollback

Every deploy is a new Cloud Run revision; the previous one stays available.

```bash
gcloud run revisions list --service saptha --region "$REGION"
gcloud run services update-traffic saptha --region "$REGION" --to-revisions=<previous-revision>=100
```

Migrations only add (columns, tables, indexes), so an older revision runs on a
newer schema. If a migration itself must be undone, run
`alembic downgrade -1` from the previous image (a migration job, as above)
**after** a backup, then roll the traffic back.

## Monitoring

- **Health:** `/health` (liveness) and `/health/ready` (the database answers)
  return 200, or 503 with no error details. Point an uptime check at
  `/health/ready`.
- **Logs:** production writes one JSON object per line, with `severity` and
  the request's trace, so Cloud Logging filters by level and groups by request.
- **Errors:** set `SENTRY_DSN` to send exceptions to Sentry (no personal data;
  the release is the Cloud Run revision).
- **Background tasks:** failed tasks wait in the `outbox` table and are retried
  by the `outbox` job; the Super Admin dashboard shows how many have failed.
- **Payments:** paid orders that couldn't complete a registration are listed
  on the Super Admin's payments page, to complete or refund.
- **Cost:** keep a budget alert on the billing account (the test used 50, 75,
  90 and 100% of the credit).

## Android app (Capacitor) build

The Capacitor Android application embeds the responsive portal in a webview wrapper.
Before syncing or building the Android APK, configure `capacitor.config.json` with the deployment `BASE_URL`:

```bash
# Generate config pointing strictly at the target host
BASE_URL="https://events.example.edu" npm run cap:config
# or directly:
BASE_URL="https://events.example.edu" python scripts/configure_capacitor.py

# Sync assets and native platform
npx cap sync android
```

This ensures `server.url` and `server.allowNavigation` in `capacitor.config.json` point strictly to your university production domain instead of retired development URLs.

## Release check

Run before each release, from a fresh clone of the branch being released, and
record the results in `docs/FEATURE_REVIEW.md` (UPG-32 has the first run's).

1. **Fresh install:** `git clone`, a new virtual environment **at `.venv` in
   the clone** (the type-check test runs `.venv/bin/python`), then
   `pip install -r requirements-dev.txt`, `python -m playwright install chromium`.
2. **Dependencies and secrets:** `pip-audit -r requirements.txt --no-deps --disable-pip`
   (and `pip-audit` on the whole environment);
   `gitleaks git --redact --exit-code 1 --gitleaks-ignore-path .gitleaksignore .`
   over the full history.
3. **Static checks:** `ruff check .`; `bandit -ll -q` over the tracked files
   outside `tests/` (CI runs both).
4. **Database:** `alembic upgrade head` on an empty PostgreSQL database, then a
   non-production seed (`python seed.py --profile showcase`, development mode).
5. **Production boot:** start the app with `FLASK_ENV=production` and strong
   dummy settings: it must serve `/` and `/health` with HSTS and a CSP nonce, and
   refuse to start, naming the problem, when one required setting is removed.
6. **Two instances and a restart:** two gunicorn instances on the same database;
   a login on one works on the other, and still works after restarting the
   first (sessions live in the database).
7. **Tests:** full `pytest` on SQLite, and again with `TEST_DATABASE_URL`
   pointing at an empty PostgreSQL database.
8. **Browser pass:** every role's key pages in headless Chromium at 375px and
   1280px against the production build (served over HTTPS), with real logins:
   no sideways scroll, nothing cut off, no script or CSP error, no failed request.
   The repo's own browser tests (`tests/headless.py` users) cover the same
   checks on every test run where Chromium is installed.
9. **Container:** `docker compose up --build` starts the app, worker and
   database (Cloud Build builds the same `Dockerfile` on deploy).

## Hackathon release (UPG-199)

The release with the hackathon portal (UPG-190 to UPG-198) and the work before it
(UPG-152 to UPG-162). Do the steps in order; each one says what you should see.
Run them in **Cloud Shell** (console.cloud.google.com, the `>_` button): gcloud on
the Mac is refused for this project.

**0. Before you start (on the Mac).** All the work must be committed and pushed to
`production-ready`, because Cloud Shell builds from GitHub, not from your Mac. The
full test suite passes on SQLite and PostgreSQL (`docs/FEATURE_REVIEW.md`, UPG-198).
Pick a quiet hour: the deploy itself takes about 15 minutes.

**1. Get the code and note today's revision (your way back).**

```bash
PROJECT=saptha-event-261017; REGION=asia-south1
gcloud config set project "$PROJECT"
rm -rf saptha && git clone --branch production-ready https://github.com/kirancodes-dev/saptha-event-portal.git saptha && cd saptha
git log -1 --oneline                       # the commit you meant to release
OLD=$(gcloud run services describe saptha --region "$REGION" --format='value(status.latestReadyRevisionName)')
echo "Rollback revision: $OLD"             # write this down
```

**2. Back up the database** (a manual backup, kept until you delete it):

```bash
SQL=$(gcloud run services describe saptha --region "$REGION" \
  --format='value(spec.template.metadata.annotations."run.googleapis.com/cloudsql-instances")')
gcloud sql backups create --instance="${SQL##*:}"
```

**3. Build the image.**

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT/saptha/web:$(git rev-parse --short HEAD)"
gcloud builds submit --tag "$IMAGE"        # ends with STATUS: SUCCESS
```

**4. Migrate the database before the new code serves.** The `saptha-migrate` job
already exists; point it at the new image and run it. It applies every migration the
database hasn't had yet: `0009_naac_roles` (if it isn't there already) and
`0010_email_quota` to `0014_source_visits`. They only add tables and a role value,
so the running (old) revision keeps working on the new schema.

```bash
gcloud run jobs update saptha-migrate --image "$IMAGE" --region "$REGION"
gcloud run jobs execute saptha-migrate --region "$REGION" --wait     # must end "successfully completed"
```

If it fails, stop here: nothing has changed for users. Read the job's log
(`gcloud run jobs executions list --job saptha-migrate --region "$REGION"`, then the
link it prints) and send the error (never a password or key) for a fix.

**5. Settings.** Three things, checked or added once:

- **Gemini key (AI scoring, UPG-192).** Make a key at aistudio.google.com (API keys),
  then store it as a secret. Paste it only into this command, never into a chat,
  email or report:

  ```bash
  read -rs GEMINI && printf '%s' "$GEMINI" | gcloud secrets create GEMINI_API_KEY --data-file=- && unset GEMINI
  ```

  Without it the app still works: the SPOC's page says AI scoring is off and the
  SPOC ranks by hand. Each AI-scored submission is one call (at most 500 per event).
- **Daily email limit (UPG-152).** `EMAIL_DAILY_LIMIT` below your mail provider's
  daily quota: 270 on Brevo's free plan, 450 on Gmail, 1,800 on Google Workspace.
- **Private files in the bucket.** Problem statement PDFs and team submissions are
  private files; in production they must go to Cloud Storage (the app refuses local
  storage). Check the service already has `STORAGE_TYPE=gcs` and `GCS_BUCKET_NAME`,
  and that the bucket uses fine-grained access (see "Uploads and private file links"):

  ```bash
  gcloud run services describe saptha --region "$REGION" --format=yaml | grep -A1 -E 'STORAGE_TYPE|GCS_BUCKET_NAME'
  gcloud storage buckets describe gs://saptha-event-261017-uploads | grep -i uniform   # must say false
  ```

**6. Deploy.** `--update-…` adds to the service's settings and keeps the rest
(`--set-env-vars` or `--set-secrets` here would **remove** every other setting):

```bash
gcloud run deploy saptha --image "$IMAGE" --region "$REGION" \
  --update-env-vars=EMAIL_DAILY_LIMIT=270 \
  --update-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest
gcloud run services describe saptha --region "$REGION" --format='value(status.latestReadyRevisionName)'   # the new revision
```

Leave out `--update-secrets` if you skipped the Gemini key. If the revision fails to
start, Cloud Run keeps serving the old one; the log names the problem.

**7. Smoke checks (about 15 minutes).** On a phone and a laptop:

1. `https://<service URL>/health/ready` answers `{"ready": true}`.
2. The login page lists Admin, SPOC, Event coordinator, Judge and Student and
   nothing else, on an **iPhone (Safari)** too (UPG-198's hand check, UPG-204).
   The home page has no "Sparky" chat button (UPG-205).
3. As a SPOC, create a test hackathon (event type Hackathon, a WhatsApp group link),
   open its hackathon page, add one problem statement released now and one 10
   minutes ahead, and a submission form that opens now and closes in 30 minutes.
4. Register a test team from a private browser window with an address you can read:
   exactly **one** email arrives, with the WhatsApp link and the portal link.
5. Log in as that lead: the team page shows the stages, the countdown and the first
   problem; 10 minutes later the second appears without anyone pressing anything.
   Submit with a small PDF (this proves private storage), then open the PDF.
6. As the SPOC, extend the deadline by 15 minutes: the team page shows the new time.
   After it closes, press "Start AI scoring": the submission gets a score (this
   proves the Gemini key). Shortlist it, then undo the shortlist.
7. As Super Admin, `/diag/email` shows today's email count.
8. Cancel or delete the test event (SPOC dashboard) so students don't see it.

**8. If something is wrong: roll back.** Send all traffic to the revision from step 1
(takes seconds; the database stays as it is, which the old revision can use):

```bash
gcloud run services update-traffic saptha --region "$REGION" --to-revisions="$OLD"=100
```

**9. Afterwards.** Send the new revision name and the commit to record in
`docs/FEATURE_REVIEW.md` (UPG-199). Keep the step 2 backup until the first real
hackathon is over.

## Go-live checklist (what only the owner can do)

Tick each before opening the portal to students.

- [ ] **Accounts and secrets:** create the production secrets in Secret Manager
  with **new** values (never ones used in the test deployment or in `.env`);
  set `SUPER_ADMIN_EMAIL`/`SUPER_ADMIN_PASS`, log in once, then remove
  `SUPER_ADMIN_PASS`.
- [ ] **Email:** create a Brevo account (or keep the Gmail app password for a
  small pilot), verify the sender address, set `BREVO_API_KEY` and `MAIL_FROM`.
  Then, as Super Admin, open `/diag/email?to=<you>`: the message must arrive,
  not in spam. Appoint a test judge and check their set-password link works.
- [ ] **Razorpay:** run one checkout in **Test Mode** end to end with the
  webhook set (Dashboard → Webhooks → `https://<BASE_URL>/payment/webhook/razorpay`,
  events `payment.captured`, `payment.authorized`, `payment.failed`,
  `refund.processed`, `refund.failed`) and a refund (UPG-30 criterion 4).
  Only then switch to the live key ID, key secret and webhook secret.
- [ ] **Sentry:** create a project and set `SENTRY_DSN`; trigger a test error
  and check it arrives without personal data.
- [ ] **Cloud Scheduler:** create the six jobs (`reminders` every hour,
  `lifecycle` every 6 hours, `cleanup` daily, `naac` and `impact` daily, `outbox` every 15 minutes) with the
  `X-Cron-Secret` header (see "Scheduled jobs"); run each once by hand and
  check it answers 200.
- [ ] **Budget alert:** a budget on the billing account with alerts at 50, 75,
  90 and 100%, sent to someone who reads them.
- [ ] **`SUPPORT_EMAIL`:** set it to a monitored address
  (`events@<university domain>`, D-4); the privacy, terms and payment-failed
  pages show it.
- [ ] **Certificates:** set `COLLEGE_NAME` (and the logo and colours if the
  defaults aren't right). For each event, the organiser adds 1–3 signatories
  with their names, titles and signature images (PNG or JPG, 1 MB or less, on
  white paper or a transparent background) on the event's certificate page;
  collect the signature scans from the people who will sign. Issue one test
  certificate and check it at `/verify/<number>`.
- [ ] **WhatsApp (optional):** a WhatsApp Business account, the four templates
  approved, the webhook set, then the provider's settings and a monthly cap
  (see "WhatsApp").
- [ ] **Campus facts:** confirm or correct the chatbot's campus facts
  (UPG-108); until then it refers campus questions to the college office.
- [ ] **Login limit:** `LOGIN_THROTTLE_IP_LIMIT=50` (many students share one
  campus IP).
- [ ] **Backups:** check Cloud SQL's daily backups are on, and run the restore
  drill once (see "Restore drill").
- [ ] **After the first deploy:** confirm signed download links work on Cloud
  Run (UPG-99 criterion 2), and that GitHub's next CI run has no "Jekyll site CI"
  check (UPG-38 criterion 2).
- [ ] **Old data:** don't reuse the test deployment's database for real
  students; if an older database is reused, reset every password first and
  force resets for walk-in accounts from the old Zoho deploy (UPG-15).
- [ ] **GitHub:** GitHub Support's removal of the old pull-request refs (BLK-01).
- [ ] **Container:** run `docker compose up --build` once on a machine with
  Docker (the release check couldn't; Cloud Build builds the same image).
