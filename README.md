<div align="center">

<img src="static/images/logo.png" width="100" alt="Sapthagiri NPS University Logo" />

# SapthaEvent

### University Event Intelligence Platform
**Sapthagiri NPS University, Bengaluru**

[![Live](https://img.shields.io/badge/🌐%20Live%20App-saptha--event--portal.xyz-6f42c1?style=for-the-badge)](https://saptha-event-portal.xyz/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![Firebase](https://img.shields.io/badge/Firestore-NoSQL-FF6F00?style=for-the-badge&logo=firebase)](https://firebase.google.com)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?style=for-the-badge&logo=google)](https://ai.google.dev)
[![CI](https://img.shields.io/github/actions/workflow/status/kirancodes-dev/saptha-event-portal/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/kirancodes-dev/saptha-event-portal/actions)

<br/>

> **[→ Open the Live App](https://saptha-event-portal.xyz/)** — Built for judges, students, and clubs. Not spreadsheets.

</div>

---

## Why SapthaEvent?

Most university event systems are glorified Google Forms. SapthaEvent is a **complete event intelligence platform** — real-time leaderboard on any projector, AI post-event reports, XP achievement engine, automated email sequences, and a Celery scheduler that works even when nobody is logged in.

| What you'd normally do | What SapthaEvent does |
|---|---|
| Google Form registration | Per-event custom form schema, team validation, payment gate |
| Paper or spreadsheet scoring | Live digital scorecard, auto-averaged across all judges |
| Manual result announcement | Real-time SSE leaderboard on any screen or projector |
| Nothing after the event | AI-generated narrative report (Gemini 2.5 Flash) + PDF export |
| No recognition for participants | XP points + emoji badges accumulated across every event |
| "Reply-all" email blasts | Per-event blast with audience filter — all / attended / winners |
| Re-fill everything for next event | One-click clone with clean slate |
| Cash or manual payment tracking | Razorpay with HMAC-SHA256 server-side verification |

---

## 🌐 Live App

**URL:** [`https://saptha-event-portal.xyz`](https://saptha-event-portal.xyz/)

| Role | Email | Password |
|---|---|---|
| Student | `student@demo.com` | `Demo1234` |
| Club SPOC | `spoc@demo.com` | `Demo1234` |
| Judge | `judge@demo.com` | `Demo1234` |
| Coordinator | `coordinator@demo.com` | `Demo1234` |

---

## ✨ Flagship Features

### ⚡ Real-Time SSE Leaderboard
`GET /live/<event_id>` — project onto any screen during the event.

- Pure Server-Sent Events — no WebSocket server, works through proxies
- Reads `scores` sub-collection from Firestore, averages across all judges, sorts by score
- Pushes ranked update every 3 seconds; client auto-reconnects after drop
- Podium view: top-3 as gold / silver / bronze cards
- Rank-change animation: rows flash green ↑ or red ↓ on each tick
- Fullscreen toggle — dark theme optimised for projectors

### 🤖 AI Event Report
`GET /spoc/ai_report/<event_id>` — one click after closing an event.

- Builds a stats payload: registrations, attendance %, judge count, avg/top score, podium
- Sends to Gemini 2.5 Flash → 3-paragraph narrative debrief
- Falls back gracefully to a data-only summary if no API key or network failure
- `@media print` CSS — print or save as PDF directly from the browser

### 🏆 Achievement & XP Engine
Triggered automatically when a SPOC ends an event.

- 🥇 **Rank 1** → Champion badge + 500 XP
- 🥈 **Rank 2** → Runner-Up badge + 300 XP
- 🥉 **Rank 3** → Third Place badge + 200 XP
- ⭐ **All scored** participants → Participant badge + 50 XP
- XP and badges accumulate across events — shown on each participant's dashboard

### 📊 SuperAdmin Control Center
- Sidebar navigation: Dashboard · Analytics · A4 Report · Blast Email · SPOC Console · Audit Log
- 6-stat overview grid: Total Events · Registrations · Revenue · Unique Staff · Club SPOCs · Students
- Searchable, filterable event table with live stats per event
- Bar + doughnut charts (registrations per event, category distribution)
- Printable A4 portal report: executive summary, events register, staff directory

---

## 🗂 Portal Sections

### 🎓 Participant Dashboard
- Register for events (custom form per event, team + solo support)
- Pay via Razorpay — webhook + HMAC verification
- Track registration status, payment receipt, QR ticket
- View accumulated XP and badge wall

### 🏢 Club SPOC Dashboard
- Create and manage events with AI-generated form schemas (Gemini)
- Set registration caps, deadlines, team sizes, payment amounts
- **Live Board** → opens SSE leaderboard in new tab
- **AI Report** → generates post-event debrief
- **Blast Email** → send custom email to all / attended / winners
- **Clone Event** → duplicate event doc + form schema, clear dates
- Export attendee CSV (name, USN, phone, score, attendance)
- QR-code scanner for attendance marking
- Revenue + staff assigned stats on dashboard

### ⚖️ Judge Interface
- Assigned to specific events by admin
- Score individual teams with per-criterion rubric
- Scores averaged server-side — no manual collation

### 🔧 Coordinator Tools
- Cross-event attendance dashboard
- QR scanner (camera or manual entry) for entry gate
- Event lifecycle controls (open/close registration, end event)

### 🛡 Admin Panel
- Create users (SPOC, Judge, Coordinator, Admin) with auto-generated passwords
- Bulk-assign judges to events
- System-wide audit log (`actions` Firestore collection)
- Email diagnostic: `GET /diag/email?to=you@email.com`
- Unique staff count (deduplicated by email across all events)

---

## 📧 Automated Email

All email is non-blocking — queued to Celery workers, delivered via **Brevo HTTP API** (no SMTP, Railway-safe).

| Trigger | What sends |
|---|---|
| Registration | Confirmation email immediately |
| Payment | Receipt with amount on Razorpay webhook |
| 3-day reminder | "Event in 3 days" at 09:00 IST |
| 24-hour reminder | "Tomorrow! Here's your ticket" at 09:00 IST |
| Velocity alert | SPOC notified if fill rate < 70% with 3 days to deadline |
| Password reset | Timed token link (1-hour TTL) |
| Blast email | Custom SPOC-authored message, on demand |

All emails include the **Sapthagiri NPS University logo and college name** in the header and link back to `https://saptha-event-portal.xyz`.

---

## 💳 Payments

- Razorpay order created server-side at registration
- Client completes payment in Razorpay modal
- Server verifies `razorpay_signature` with HMAC-SHA256 before writing `payment_status: paid`
- Amount and `order_id` always fetched from Firestore — no client-side trust

---

## ⏰ Scheduled Tasks (Celery Beat)

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

## 🏗 Architecture

```
Browser ──HTTPS──▶ saptha-event-portal.xyz (Railway / Gunicorn)
                        │
                   Flask App
                   ├── routes_auth.py          Login / Register / Password Reset
                   ├── routes_participant.py   Student dashboard, registration, payment
                   ├── routes_spoc.py          SPOC dashboard, AI report, blast, clone
                   ├── routes_judge.py         Scoring interface
                   ├── routes_coordinator.py   Attendance, scanner
                   ├── routes_admin.py         User management, audit log, A4 report
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
                   Gemini 2.5 Flash (AI reports)
                   Brevo HTTP API   (Email delivery)
```

---

## 🗺 Blueprint Map

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

## 🔧 Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 3.x + Gunicorn |
| Database | Google Firestore (NoSQL) |
| Task queue | Celery 5 + Redis (prod) / APScheduler (dev) |
| AI / LLM | Google Gemini 2.5 Flash |
| Payments | Razorpay |
| Email | Brevo HTTP API (Railway-safe, no SMTP port restrictions) |
| Auth tokens | itsdangerous URLSafeTimedSerializer |
| Password hashing | Werkzeug scrypt |
| CSRF | Flask-WTF |
| Frontend | Bootstrap 5 + Jinja2 + Vanilla JS |
| QR codes | qrcode[pil] |
| PDF generation | ReportLab |
| Deployment | Railway (web + worker + beat services) |
| CI | GitHub Actions (Ruff lint + Bandit security scan + pytest) |

---

## 🚀 Local Setup

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

# Email — Brevo HTTP API (recommended, no port restrictions)
BREVO_API_KEY=your-brevo-api-key
MAIL_FROM=SapthaEvent <noreply@snpsu.edu.in>
```

### 3 — Place Firebase key

Drop your `serviceAccountKey.json` into the project root (already gitignored).

### 4 — First-run admin account

On first boot the SuperAdmin Firestore document may not exist. Run this once to create it:

```bash
python fix_superadmin.py
```

Log in at `http://127.0.0.1:5001/login` with:
- **Role:** Super Admin
- **Email:** value of `SUPER_ADMIN_EMAIL` in `.env`
- **Password:** `Admin@12345` (change after first login)

### 5 — Start the server

```bash
python app.py
# Runs on http://127.0.0.1:5001
```

APScheduler runs in-process — no Redis or Celery worker needed locally.

### 6 — Verify email works locally

With the app running, open:

```
http://127.0.0.1:5001/diag/email?to=your@email.com
```

Returns JSON with `"sent": true` if Brevo is working, or an error message if not.

---

## ☁️ Production Deploy (Railway)

### Services (Procfile)

```
web:    gunicorn app:app
worker: celery -A celery_app worker --loglevel=info
beat:   celery -A celery_app beat --loglevel=info
```

### Required Railway Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret (long random string) |
| `MASTER_SECRET_KEY` | SuperAdmin login gate key |
| `SUPER_ADMIN_EMAIL` | SuperAdmin email address |
| `SUPER_ADMIN_PASS` | SuperAdmin default password |
| `FIREBASE_CREDENTIALS` | Full `serviceAccountKey.json` as a JSON string |
| `CELERY_BROKER_URL` | Redis URL — e.g. `redis://default:pass@host:6379/0` |
| `BASE_URL` | `https://saptha-event-portal.xyz` |
| `FLASK_ENV` | `production` |
| `BREVO_API_KEY` | Brevo (Sendinblue) API key — email delivery |
| `MAIL_FROM` | Sender — `SapthaEvent <noreply@snpsu.edu.in>` |
| `GEMINI_API_KEY` | Google Gemini API key |
| `RAZORPAY_KEY_ID` | Razorpay public key |
| `RAZORPAY_KEY_SECRET` | Razorpay secret (server-side only) |

---

## 👤 Role System

| Role | Login dropdown | Dashboard URL |
|---|---|---|
| `Student` | Student | `/participant/dashboard` |
| `ClubSPOC` | Club SPOC | `/spoc/dashboard` |
| `Judge` | Judge | `/judge/dashboard` |
| `Coordinator` | Coordinator | `/coordinator/dashboard` |
| `EventCoordinator` | Coordinator | `/coordinator/scanner` |
| `Admin` | Admin | `/admin/dashboard` |
| `SuperAdmin` | Super Admin | `/admin/dashboard` (full access — all roles) |

> SuperAdmin is a wildcard role: access to every dashboard and action. Requires the master key in production. Cannot be reset via email — by design.

---

## 🔒 Security

- All passwords hashed with `scrypt` via Werkzeug — legacy plaintext rows are **blocked at login** (not silently accepted)
- CSRF protection on all HTML form endpoints (Flask-WTF)
- Password reset via timed, signed token — 1-hour TTL (`itsdangerous`)
- Razorpay payment amounts verified server-side via HMAC-SHA256
- SuperAdmin cannot be reset via email
- Session lifetime server-controlled (1 hour)
- **Ruff** (linter) + **Bandit** (security scanner) + **pytest** run on every push via GitHub Actions

---

## ⚙️ CI / CD

- **GitHub Actions:** `ruff check` + `bandit -r .` + `pytest` on every push and PR
- **Railway:** auto-deploys on push to `main` — three services: web, worker, beat

---

## 🗃 Project Structure

```
saptha-event-portal/
├── app.py                    # App factory, blueprint registration, CSRF, Razorpay
├── models.py                 # Firestore client init
├── config.py                 # All configuration — reads from env vars
├── celery_app.py             # Celery config + Beat schedule
├── scheduler.py              # APScheduler (dev mode, in-process)
├── utils.py                  # log_action, shared helpers, role_required decorator
├── utils_email.py            # Brevo HTTP API email delivery
├── utils_certificate.py      # PDF certificate generation
├── utils_qr.py               # QR code helpers
│
├── routes_auth.py            # Login, register, password reset, logout
├── routes_participant.py     # Student dashboard, registration, payment webhook
├── routes_spoc.py            # SPOC dashboard, AI report, blast, clone, achievements
├── routes_judge.py           # Scoring interface
├── routes_coordinator.py     # Attendance, scanner
├── routes_admin.py           # User/event management, audit log, A4 report
├── routes_live.py            # SSE leaderboard stream + projector page
├── routes_forms.py           # AI form schema generation (Gemini)
├── routes_public.py          # Home, event listings, search/filter
├── routes_ticket.py          # QR ticket + PDF
│
├── tasks/
│   ├── analytics_tasks.py    # Celery: daily stats rollup
│   ├── webhook_tasks.py      # Celery: payment confirmation emails
│   └── scheduled_tasks.py    # Celery: reminders, velocity alert, lifecycle
│
├── templates/                # Jinja2 HTML templates per blueprint
│   ├── admin/
│   │   ├── dashboard.html    # SuperAdmin control center (sidebar, charts, event table)
│   │   └── report.html       # A4 printable portal report
│   └── spoc/
│       └── dashboard.html    # SPOC dashboard (revenue, staff, Admin HQ link)
├── static/                   # CSS, JS, images (college logo)
├── fix_superadmin.py         # One-shot: reset SuperAdmin in Firestore (run locally)
├── Procfile                  # Railway: web + worker + beat
├── requirements.txt
├── ruff.toml                 # Linting config
└── .github/workflows/ci.yml  # Ruff + Bandit + pytest CI
```

---

## 🛠 Troubleshooting

**Login redirects back to `/login` without error**  
The Firestore account has a legacy plaintext password. Run `python fix_superadmin.py` to reset it with a proper hash.

**Emails not sending**  
Hit `/diag/email?to=your@email.com` — the JSON response shows the exact error. Check that `BREVO_API_KEY` is set correctly in Railway environment variables.

**Email links point to the wrong URL**  
Set `BASE_URL=http://127.0.0.1:5001` in `.env` locally, or `BASE_URL=https://saptha-event-portal.xyz` in Railway production variables.

**Staff count shows 400+ (double-counting)**  
Fixed in the current release: staff are now deduplicated by email set across all events before counting.

**Celery tasks not running locally**  
APScheduler runs in-process when `CELERY_BROKER_URL` is not set — no worker needed. If you need to test Celery explicitly, start Redis and run `celery -A celery_app worker`.

---

## 🔗 Links

| | |
|---|---|
| **Live App** | [https://saptha-event-portal.xyz](https://saptha-event-portal.xyz/) |
| **GitHub** | [github.com/kirancodes-dev/saptha-event-portal](https://github.com/kirancodes-dev/saptha-event-portal) |
| **University** | [snpsu.edu.in](https://snpsu.edu.in) — Sapthagiri NPS University, Bengaluru |

---

<div align="center">

Flask &nbsp;·&nbsp; Firestore &nbsp;·&nbsp; Celery &nbsp;·&nbsp; Gemini AI &nbsp;·&nbsp; Razorpay &nbsp;·&nbsp; Brevo &nbsp;·&nbsp; Railway

**SapthaEvent — because spreadsheets don't belong at hackathons.**

</div>
