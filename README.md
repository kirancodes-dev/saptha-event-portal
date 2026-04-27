<div align="center">

# SapthaEvent

**University Event Intelligence Platform — Sapthagiri NPS University**

[![Live](https://img.shields.io/badge/Live-saptha--event--portal--production.up.railway.app-purple?style=for-the-badge&logo=railway)](https://saptha-event-portal-production.up.railway.app/)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![Firebase](https://img.shields.io/badge/Firestore-NoSQL-orange?style=for-the-badge&logo=firebase)](https://firebase.google.com)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5%20Flash-teal?style=for-the-badge&logo=google)](https://ai.google.dev)

**[🌐 Open Live App](https://saptha-event-portal-production.up.railway.app/)** &nbsp;·&nbsp; Built for judges, students, and clubs — not spreadsheets.

</div>

---

## Why SapthaEvent

Most university event systems are glorified Google Forms. SapthaEvent is a complete event intelligence platform — real-time leaderboard on any projector, AI post-event reports, XP/achievement engine, automated email sequences, and a Celery scheduler that works even when nobody is logged in.

| Feature | Typical System | SapthaEvent |
|---|---|---|
| Registration | Google Form | Per-event custom form schema, team validation, payment gate |
| Scoring | Paper or spreadsheet | Live digital scorecard, auto-averaged across judges |
| Results | Manually announced | Real-time SSE leaderboard on any screen/projector |
| Post-event report | Nothing | AI-generated narrative (Gemini 2.5 Flash) + PDF export |
| Achievements | Nothing | XP points + emoji badges on each participant's profile |
| Reminders | Manual | Celery Beat: 3-day + 24 h automated email sequences |
| Email blast | CC everyone | Per-event blast with audience filter (all / attended / winners) |
| Event cloning | Re-fill everything | One-click clone with clean slate |
| Payments | Nothing | Razorpay with HMAC-SHA256 server-side verification |

---

## Live App

**URL:** `https://saptha-event-portal-production.up.railway.app/`

| Role | Email | Password |
|---|---|---|
| Student | `student@demo.com` | `Demo1234` |
| Club SPOC | `spoc@demo.com` | `Demo1234` |
| Judge | `judge@demo.com` | `Demo1234` |
| Coordinator | `coordinator@demo.com` | `Demo1234` |

---

## Flagship Features

### 1 — Real-Time SSE Leaderboard
`GET /live/<event_id>` — project onto any screen during the event.

- Pure Server-Sent Events — no WebSocket server, works through proxies
- Reads `scores` sub-collection from Firestore, averages across all judges, sorts by score
- Pushes ranked update every 3 seconds; client auto-reconnects after drop
- Podium view: top-3 as gold/silver/bronze cards (`order: 2,1,3`)
- Rank-change animation: rows flash green ↑ or red ↓ on each tick
- Fullscreen toggle — dark theme (`#05050f`) optimised for projectors

### 2 — AI Event Report
`GET /spoc/ai_report/<event_id>` — one click after closing an event.

- Builds a stats payload: registrations, attendance %, judge count, avg/top score, podium
- Sends to Gemini 2.5 Flash → 3-paragraph narrative debrief
- Falls back gracefully to a data-only summary if no API key or network failure
- `@media print` CSS — print or save as PDF directly from browser

### 3 — Achievement & XP Engine
Triggered automatically when a SPOC ends an event.

- Rank 1 → 🥇 Champion + 500 XP
- Rank 2 → 🥈 Runner-Up + 300 XP
- Rank 3 → 🥉 Third Place + 200 XP
- All scored participants → ⭐ Participant + 50 XP
- XP and badges accumulate across events — shown on each participant's dashboard

---

## Portal Sections

### Participant Dashboard
- Register for events (custom form per event, team + solo support)
- Pay via Razorpay — webhook + HMAC verification
- Track registration status, payment receipt, QR ticket
- View accumulated XP and badge wall

### Club SPOC Dashboard
- Create and manage events with AI-generated form schemas (Gemini)
- Set registration caps, deadlines, team sizes, payment amounts
- Live Board → opens SSE leaderboard in new tab
- AI Report → generates post-event debrief
- Blast Email → send custom email to all / attended / winners
- Clone Event → duplicate event doc + form schema, clear dates
- Export attendee CSV (name, USN, phone, score, attendance)
- QR-code scanner for attendance marking

### Judge Interface
- Assigned to specific events by admin
- Score individual teams with per-criterion rubric
- Scores averaged server-side — no manual collation

### Coordinator Tools
- Cross-event attendance dashboard
- QR scanner (camera or manual entry) for entry gate
- Event lifecycle controls (open/close registration, end event)

### Admin Panel
- Create users (SPOC, Judge, Coordinator, Admin) with auto-generated passwords
- Bulk-assign judges to events
- System-wide audit log (`actions` Firestore collection)
- Email diagnostic: `GET /diag/email?to=you@email.com`

---

## Automated Email

All email is non-blocking — queued to Celery workers.

| Trigger | What sends |
|---|---|
| Registration | Confirmation email immediately |
| Payment | Receipt with amount on Razorpay webhook |
| 3-day reminder | "Event in 3 days" at 09:00 IST |
| 24-hour reminder | "Tomorrow! Here's your ticket" at 09:00 IST |
| Velocity alert | SPOC notified if fill rate < 70% with 3 days to deadline |
| Password reset | Timed token link (1-hour TTL) |
| Blast email | Custom SPOC-authored message, on demand |

**Providers (auto-detected from env):**
- `RESEND_API_KEY` set → uses Resend API (recommended for Railway free plan)
- `RESEND_API_KEY` not set → falls back to Gmail SMTP (`MAIL_USER` + `MAIL_PASS`)

---

## Payments

- Razorpay order created server-side at registration
- Client completes payment in Razorpay modal
- Server verifies `razorpay_signature` with HMAC-SHA256 before writing `payment_status: paid`
- Amount and `order_id` always fetched from Firestore — no client-side trust

---

## Scheduled Tasks (Celery Beat)

```
09:00 IST  send_3day_reminders          email participants 3 days before event
09:00 IST  send_24h_reminders           email participants 24 h before event
09:45 IST  check_registration_velocity  alert SPOC if fill < 70% with 3 days to deadline
00:00 IST  auto_close_registrations     close registrations past deadline
00:00 IST  archive_past_events          move ended events to archive
```

Dev mode uses APScheduler (in-process) — no Redis or worker needed locally.  
Production uses `celery -A celery_app worker` + `celery -A celery_app beat`.

---

## Architecture

```
Browser ──HTTPS──▶ Railway (Gunicorn)
                        │
                   Flask App
                   ├── routes_auth.py          Login / Register / Password Reset
                   ├── routes_participant.py   Student dashboard, registration, payment
                   ├── routes_spoc.py          SPOC dashboard, AI report, blast, clone
                   ├── routes_judge.py         Scoring interface
                   ├── routes_coordinator.py   Attendance, scanner
                   ├── routes_admin.py         User management, audit log
                   ├── routes_live.py          SSE leaderboard stream
                   ├── routes_forms.py         AI form schema generation
                   ├── routes_public.py        Home, event listings
                   └── routes_ticket.py        QR ticket + PDF
                        │
          ┌─────────────┼────────────────┐
          ▼             ▼                ▼
    Firestore       Celery Worker    Razorpay API
    (NoSQL)         + Beat           (Payments)
                        │
                      Redis (prod)
                   APScheduler (dev)
                        │
                   Gemini 2.5 Flash
                   Resend / Gmail SMTP
```

---

## Blueprint Map

| Blueprint | Prefix | Roles |
|---|---|---|
| `auth_bp` | `/` | Public |
| `public_bp` | `/` | Public |
| `participant_bp` | `/participant` | Student |
| `spoc_bp` | `/spoc` | ClubSPOC |
| `judge_bp` | `/judge` | Judge |
| `coordinator_bp` | `/coordinator` | Coordinator, EventCoordinator |
| `admin_bp` | `/admin` | Admin, SuperAdmin |
| `live_bp` | `/live` | Public (projector) |
| `forms_bp` | `/forms` | ClubSPOC |
| `ticket_bp` | `/ticket` | Authenticated |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 3.x + Gunicorn |
| Database | Google Firestore (NoSQL) |
| Task queue | Celery 5 + Redis (prod) / APScheduler (dev) |
| AI / LLM | Google Gemini 2.5 Flash |
| Payments | Razorpay |
| Email | Resend API / Gmail SMTP (auto-detected) |
| Auth tokens | itsdangerous URLSafeTimedSerializer |
| Password hashing | Werkzeug scrypt |
| CSRF | Flask-WTF |
| Frontend | Bootstrap 5 + Jinja2 + Vanilla JS |
| QR codes | qrcode[pil] |
| PDF generation | ReportLab |
| Deployment | Railway (web + worker + beat services) |
| CI | GitHub Actions (Ruff lint + Bandit security scan) |

---

## Local Setup

### 1 — Clone and install

```bash
git clone https://github.com/kirancodes-dev/saptha-event-portal.git
cd saptha-event-portal
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Create `.env`

```bash
cp .env.example .env   # then fill in the values below
```

Minimum `.env` for local development:

```env
SECRET_KEY=any-random-string-here
SUPER_ADMIN_EMAIL=admin@snpsu.edu.in
SUPER_ADMIN_PASS=YourLocalPassword1
MASTER_SECRET_KEY=any-local-master-key
BASE_URL=http://127.0.0.1:5001
GEMINI_API_KEY=your-gemini-key

# Email — Gmail SMTP (local fallback, no RESEND_API_KEY set)
MAIL_USER=your@gmail.com
MAIL_PASS=your-16-char-app-password   # myaccount.google.com/apppasswords
```

> **Gmail App Password:** Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create one named "SapthaEvent", paste the 16 characters (no spaces) as `MAIL_PASS`. 2-Step Verification must be enabled first.

### 3 — Place Firebase key

Drop your `serviceAccountKey.json` into the project root (already gitignored).

### 4 — First-run admin account

On first boot the SuperAdmin Firestore document may not exist or may have a legacy plaintext password. Run this once to create/reset it:

```bash
python fix_superadmin.py
```

Output shows the credentials. Log in at `http://127.0.0.1:5001/login` with:
- **Role:** Super Admin
- **Email:** value of `SUPER_ADMIN_EMAIL` in `.env`
- **Password:** `Admin@12345` (change it after first login)

### 5 — Start the server

```bash
python app.py
# Runs on http://127.0.0.1:5001
```

APScheduler runs in-process — no Redis or Celery worker needed locally.

### 6 — Verify email works locally

With the app running, open:

```
http://127.0.0.1:5001/diag/email?to=your@gmail.com
```

Returns JSON with `"sent": true` if Gmail SMTP is working, or an error message if not.

---

## Production Deploy (Railway)

### Services (Procfile)

```
web:    gunicorn app:app
worker: celery -A celery_app worker --loglevel=info
beat:   celery -A celery_app beat --loglevel=info
```

### Required Railway Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret (long random string) |
| `MASTER_SECRET_KEY` | SuperAdmin login gate key |
| `SUPER_ADMIN_EMAIL` | SuperAdmin email address |
| `SUPER_ADMIN_PASS` | SuperAdmin default password |
| `FIREBASE_CREDENTIALS` | Full `serviceAccountKey.json` as a JSON string |
| `CELERY_BROKER_URL` | Redis URL — e.g. `redis://default:pass@host:6379/0` |
| `BASE_URL` | `https://saptha-event-portal-production.up.railway.app` |
| `FLASK_ENV` | `production` |
| `RESEND_API_KEY` | Resend API key (preferred email provider on free plan) |
| `MAIL_FROM` | Sender — `SapthaEvent <noreply@snpsu.edu.in>` after domain verified |
| `MAIL_USER` | Gmail address (fallback if no `RESEND_API_KEY`) |
| `MAIL_PASS` | Gmail 16-char App Password (no spaces) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `RAZORPAY_KEY_ID` | Razorpay public key |
| `RAZORPAY_KEY_SECRET` | Razorpay secret (server-side only) |

**Email provider logic:**
- `RESEND_API_KEY` set → Resend (works on Railway free plan, no port restrictions)
- `RESEND_API_KEY` not set → Gmail SMTP on port 465/SSL

---

## Role System

| Role | Login dropdown | Dashboard URL |
|---|---|---|
| `Student` | Student | `/participant/dashboard` |
| `ClubSPOC` | Club SPOC | `/spoc/dashboard` |
| `Judge` | Judge | `/judge/dashboard` |
| `Coordinator` | Coordinator | `/coordinator/dashboard` |
| `EventCoordinator` | Coordinator | `/coordinator/scanner` |
| `Admin` | Admin | `/admin/dashboard` |
| `SuperAdmin` | Super Admin | `/admin/dashboard` |

> SuperAdmin requires the master key in production. Cannot be reset via email — by design.

---

## Security

- All passwords hashed with `scrypt` via Werkzeug — legacy plaintext rows are **blocked at login** (not silently accepted)
- CSRF protection on all HTML form endpoints (Flask-WTF)
- Password reset via timed, signed token — 1-hour TTL (`itsdangerous`)
- Razorpay payment amounts verified server-side via HMAC-SHA256
- SuperAdmin cannot be reset via email
- Session lifetime server-controlled (1 hour)
- Ruff (linter) + Bandit (security scanner) run on every push via GitHub Actions

---

## CI / CD

- **GitHub Actions:** `ruff check` + `bandit -r .` on every push and PR
- **Railway:** auto-deploys on push to `main` — three services: web, worker, beat

---

## Project Structure

```
Event_Portel/
├── app.py                    # App factory, blueprint registration, CSRF, Razorpay
├── models.py                 # Firestore client init
├── config.py                 # All configuration — reads from env vars
├── celery_app.py             # Celery config + Beat schedule
├── scheduler.py              # APScheduler (dev mode, in-process)
├── utils.py                  # log_action, shared helpers
├── utils_email.py            # Resend / Gmail SMTP auto-switch
├── utils_certificate.py      # PDF certificate generation
├── utils_qr.py               # QR code helpers
│
├── routes_auth.py            # Login, register, password reset, logout
├── routes_participant.py     # Student dashboard, registration, payment webhook
├── routes_spoc.py            # SPOC dashboard, AI report, blast, clone, achievements
├── routes_judge.py           # Scoring interface
├── routes_coordinator.py     # Attendance, scanner
├── routes_admin.py           # User/event management, audit log
├── routes_live.py            # SSE leaderboard stream + projector page
├── routes_forms.py           # AI form schema generation (Gemini)
├── routes_public.py          # Home, event listings, search/filter
├── routes_ticket.py          # QR ticket + PDF
│
├── tasks/
│   └── scheduled_tasks.py    # Celery tasks — reminders, velocity alert, lifecycle
│
├── templates/                # Jinja2 HTML templates per blueprint
├── static/                   # CSS, JS, images
├── fix_superadmin.py         # One-shot: reset SuperAdmin in Firestore (run locally)
├── Procfile                  # Railway: web + worker + beat
├── requirements.txt
└── .github/workflows/ci.yml  # Ruff + Bandit CI
```

---

## Troubleshooting

**Login redirects back to `/login` without error**
The Firestore account has a legacy plaintext password. Run `python fix_superadmin.py` to reset it with a proper hash.

**Emails not sending locally**
Hit `http://127.0.0.1:5001/diag/email?to=your@gmail.com` — the JSON response shows the exact error. Most common cause: expired Gmail App Password. Generate a new one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

**Email links point to wrong URL**
Set `BASE_URL=http://127.0.0.1:5001` in `.env` (note port 5001, not 5000).

**Celery tasks not running locally**
APScheduler runs in-process when `CELERY_BROKER_URL` is not set — no worker needed. If you need to test Celery explicitly, start Redis and run `celery -A celery_app worker`.

---

## Repository

**GitHub:** `https://github.com/kirancodes-dev/saptha-event-portal`  
**Production:** `https://saptha-event-portal-production.up.railway.app/`  
**University:** Sapthagiri NPS University, Bengaluru — `snpsu.edu.in`

---

<div align="center">
Flask · Firestore · Celery · Gemini · Razorpay · Railway<br>
<sub>SapthaEvent — because spreadsheets don't belong at hackathons.</sub>
</div>
