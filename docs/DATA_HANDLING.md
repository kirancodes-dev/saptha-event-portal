# Personal data: what SapthaEvent holds, where it goes, and what a person can do

This page describes what the code does today. It is a factual description for
the institution's administrators and reviewers, not a legal opinion and not a
statement of compliance with any law. Questions that need a legal or policy
decision are listed at the end.

Related: [SECURITY.md](SECURITY.md), [PWA.md](PWA.md),
[INSTITUTION_SETUP.md](INSTITUTION_SETUP.md), the public notice at `/privacy`
(`templates/public/privacy.html`, version in
`services_privacy.PRIVACY_NOTICE_VERSION`).

## What is held

| Data | About whom | Where |
|---|---|---|
| Account: name, email, role, password hash, and for students USN, department, year, section, phone, CGPA and backlogs when the roster or the student supplied them | Everyone with an account | `users` |
| Registrations: the lead and each team member's name, email, phone and USN; the answers to the event's form; the ticket; attendance; any result | People who register | `registrations`, `form_submissions` |
| Feedback: a rating, tags and an optional comment, with the name and email of who gave it | Attendees who answer | `feedback_responses` |
| Website feedback rounds: the answers (ratings, ticks, optional writing, the day, the kind of device, and the event names when the round is for chosen events) are stored without the person's name or email. A separate note says who has answered a round (email, round, day) so they are not asked again; the two are not linked | Participants asked by a round the Super Admin turns on | `site_feedback_answers`, `site_feedback_done`, `site_feedback_rounds` |
| Certificates: the name printed, the event, the number, the PDF file | People a certificate was issued to | `certificates` (SQL), private file storage |
| Payments: order and payment references for paid events. Card and UPI details are entered on the payment provider's page and are not stored here | People who pay | payment records (not changed by this work) |
| Consent: which notice version was accepted and when; WhatsApp opt-in | Everyone with an account | `user_consent`, `users` |
| Notifications, and push subscriptions for people who allowed them | Account holders | `notifications_v2`, `push_subscriptions` |
| Audit log: who did what and when, with the IP address on some entries | Staff and account holders | `audit_log` |
| Sessions and failed sign-in counters (hashed keys) | Anyone signing in | `flask_sessions`, `login_attempts` or Redis |
| A student roster file while it waits to be confirmed (at most one hour, readable only by the administrator who uploaded it) | Students in the file | `roster_imports` |
| Run sheet: the name typed as responsible for a schedule item, and a staff note | Event staff | `run_sheets` |

## Who else receives data

Only the services a deployment has configured receive anything.

| Service | What it receives | When |
|---|---|---|
| Google Cloud | Everything above: it hosts the application, the database and the files | Always (current deployment; see [DEPLOY.md](DEPLOY.md)) |
| Brevo and/or Google (Gmail SMTP) | The recipient's email address and the email's content (name, event, ticket or certificate link) | Each email |
| Razorpay | What the payment page needs for a paid registration | Paid events only |
| Meta (WhatsApp Cloud API) or Twilio | The phone number and the message | Only when WhatsApp is configured and the person opted in |
| Google (Sign in with Google) | The sign-in itself | Only when a person chooses it |
| Google (Gemini) | The text a person or organiser gives an AI feature (the chatbot, drafting and matching helpers). What each feature sends has not been reviewed feature by feature | Only when an AI key is configured and the feature is used |
| Web push services (the browser vendor's) | The notification's content | Only for people who allowed notifications |

No data is sold, and nothing is sent to advertising or analytics services by
the code.

## Files

| File | Access | Where |
|---|---|---|
| Certificate PDFs, signature images, certificate backgrounds, event documents, hackathon problem statements and submissions, report evidence | Private: served by the application after a permission check, or through a link that expires | `utils_storage.put_private` |
| Profile pictures | Public by their address (an unguessable name) | `utils_storage.upload_file` |
| Exports (CSV, Excel) | Built on request and sent straight to the person who asked; not kept on the server | `services_export.py` |

Files live in the bucket the deployment configures (`STORAGE_TYPE` `s3` or
`gcs`). With neither, they are on the server's own disk, which a redeploy can
erase; the setup page's readiness list says so. Deleting an account does not
delete that person's uploaded files (their profile picture, a hackathon
submission): see "Not reached" below.

## Backups and restore: who is responsible

The application does not back itself up. The repository provides the tools
and the deployment's operator runs them:

- `scripts/backup_db.sh` dumps the whole database to a private bucket and
  deletes dumps older than `BACKUP_RETENTION_DAYS` (default 30). It runs from
  the scheduled workflow `.github/workflows/backup.yml` or a scheduled cloud
  job, and does nothing until its secrets are set.
- `scripts/restore_db.sh` restores a dump into an empty database.
  [DEPLOY.md](DEPLOY.md) describes a restore drill to run before launch and
  each term.
- The file bucket is not covered by the database dump. Copying or versioning
  it is the operator's job, in the cloud console.

Whether backups are switched on for a given deployment, where they are kept
and who can read them cannot be seen from this repository: confirm it with
the operator. A backup holds every person's data, including data of people
whose accounts were deleted after the dump was taken, until the dump expires.

## Settings this depends on

| Setting | Effect on personal data |
|---|---|
| `STORAGE_TYPE`, bucket settings | Where files are kept |
| `BREVO_API_KEY` / `MAIL_USER` and password | Which mail provider receives addresses and message content |
| `WHATSAPP_PROVIDER`, `META_WA_*` / `TWILIO_*` | Whether phone numbers are sent to a WhatsApp provider |
| `OAUTH_GOOGLE_CLIENT_ID` and secret, `GOOGLE_ALLOWED_DOMAIN` | Sign in with Google, and which email domains may use it |
| `GEMINI_API_KEY` | Whether AI features send text to Google |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Push notifications |
| `CRON_SECRET` and the scheduler | The cleanup job that carries out due deletions; without it, a deletion request is never carried out |
| `BACKUP_BUCKET`, `BACKUP_RETENTION_DAYS` | Backups and how long they are kept |
| Support email (Admin → Institution setup) | The contact shown on the privacy notice and the About page |

Secret values are set in the deployment's secret store, never in the
repository ([DEPLOY.md](DEPLOY.md)).

## Who to contact

The privacy notice and the About page (`/about`) show the support address
saved at Admin → Institution setup. That is the contact for a privacy request
and for reporting a security problem. If none is saved, the pages say so
instead of showing an address; the readiness list flags it.

## How long it is kept

The code enforces only these:

| Data | Kept |
|---|---|
| A waiting roster file | One hour, or until confirmed or cancelled |
| Sessions | 2 hours, or 30 days with "keep me signed in"; expired ones are purged by the cleanup job |
| Failed sign-in counters, email outbox, form submission keys | Purged by the cleanup job |
| An account after a deletion request | 30 days (the request can be cancelled), then removed as described below |
| Scans kept on a scanner's device | Until sent, or sign-out ([PWA.md](PWA.md)) |

Everything else (registrations, attendance, results, certificates, payments,
the audit log) is kept until someone deletes it. No job removes it after a
set period. The public notice's sentence on retention periods is therefore a
policy statement that the institution must either carry out by hand or have
built; see "Questions for human review".

## What a person can do

Signed in, at Privacy & data (`/compliance/settings`):

**Download my data** (`POST /compliance/export-data`) gives a JSON file with:
the profile (without the password hash or two-factor secrets), every
registration they lead or are a member of (other team members' details
removed), form submissions, feedback, certificates issued to them (what each
says, not the PDF), notifications, consent, and which website feedback rounds
they answered (not the answers, which are not linked to them). The download is recorded in the
audit log.

**Delete my account** (`POST /compliance/delete-request`) schedules deletion
in 30 days; it can be cancelled until then. When it is carried out:

| Removed or anonymised | Kept |
|---|---|
| The account and consent record are deleted | Certificates already issued, with the name printed on them, so a certificate that was handed out can still be verified |
| On registrations: name → "Deleted user", email → a placeholder, phone, USN and form answers cleared | Payment records |
| Form submissions: name, email, phone and answers cleared | The audit log |
| Feedback: name, email and comment removed; the rating and tags stay, with no link to the person | Attendance and result rows, without the person's name |
| Notifications deleted | |
| The note of which website feedback rounds they answered is deleted | Their website feedback answers, which never held their name or email |

**Not reached by the download or the deletion today** (logged as an open item
in FEATURE_REVIEW.md): session stars and session attendance, live poll votes
and questions asked, push subscriptions, project submissions, exam attempts,
waitlist entries, the separate ticket and check-in rows, and files the
person uploaded (profile picture, hackathon submissions). An administrator
who must remove these for a person has to do it in the database and the
bucket.

## What organisers and administrators can do with other people's data

- Exports (registration lists, attendance, certificates, the event summary
  report) need the `export_data` or `view_analytics` permission on that event
  and are recorded in the audit log. The event summary report holds counts
  only, no names.
- The student roster import shows what will change before anything is
  written, and never changes staff accounts
  ([INTEGRATIONS.md](INTEGRATIONS.md)).
- Public pages show an event's details, never its registrations. One open
  item: the public `GET /api/v1/events/<id>` returns the event's staff list
  with email addresses.

## On a device

A scanner's phone keeps unsent scans (ticket token, event, time) and the
event's entry list until sign-out; nothing else personal. Details in
[PWA.md](PWA.md).

## Questions for human review

These are decisions for the institution and its legal adviser. Nothing in the
code settles them.

1. **Retention.** The public notice states retention periods; the code deletes
   nothing on a schedule except the items in "How long it is kept". Decide the
   periods, then either have them built or remove the statement.
2. **Legal references.** The notice names the IT Act and the DPDP Act, 2023.
   Whether the wording, the grievance contact and the notice as a whole meet
   those laws has not been reviewed by a lawyer.
3. **Certificates after deletion.** Issued certificates keep the person's
   name after their account is deleted. Decide whether that is right for an
   erasure request.
4. **Minimum age** in the terms, and consent for minors.
5. **Where data is stored.** The notice no longer says "stored in India",
   because that depends on the deployment's region, which this repository
   cannot prove. Confirm the region in the cloud console before stating it.
6. **Statements about the payment provider** in the notice and the refund
   terms were left as they were (payment text is outside this work) and
   should be checked against the provider's current documents.
7. **AI features.** Decide whether text typed into them may go to Google's
   Gemini service, and say so in the notice once each feature's data flow has
   been reviewed.
8. **Audit log retention and IP addresses.** The log is kept indefinitely.
