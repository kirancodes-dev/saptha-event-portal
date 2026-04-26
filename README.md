<div align="center">

# SapthaEvent — University Event Intelligence Platform

**Sapthagiri NPS University · Full-Stack Event Management · Production-Grade**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Railway-purple?style=for-the-badge&logo=railway)](https://saptha-event-portal-production.up.railway.app/)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![Firebase](https://img.shields.io/badge/Firestore-NoSQL-orange?style=for-the-badge&logo=firebase)](https://firebase.google.com)
[![Celery](https://img.shields.io/badge/Celery-Beat-green?style=for-the-badge&logo=celery)](https://docs.celeryq.dev)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5%20Flash-teal?style=for-the-badge&logo=google)](https://ai.google.dev)

**[🌐 Open Live App](https://saptha-event-portal-production.up.railway.app/)** · Built for judges, students, and clubs — not spreadsheets.

</div>

---

## What Makes SapthaEvent Different

Most university event systems are glorified Google Forms. SapthaEvent is a full event intelligence platform — with a real-time projector leaderboard, AI-written post-event reports, an achievement/XP engine, automated email campaigns, and a Celery-powered scheduler that runs even when no one is logged in.

| Feature | Typical System | SapthaEvent |
|---|---|---|
| Registration | Google Form | Per-event custom form schema, team validation, payment gate |
| Scoring | Paper or spreadsheet | Live digital scorecard, auto-averaged across judges |
| Results | Manually announced | Real-time SSE leaderboard on any screen/projector |
| Post-event report | Nothing | AI-generated narrative (Gemini 2.5 Flash) + PDF export |
| Achievements | Nothing | XP points + emoji badges written to each participant's profile |
| Reminders | Manual | Celery Beat: 3-day + 24h automated email sequences |
| Email blast | CC everyone | Per-event blast with audience filter (all / attended / winners) |
| Event cloning | Re-fill everything | One-click clone with clean slate |
| Payments | Nothing | Razorpay with HMAC-SHA256 server-side verification |

---

## Live Demo

**URL:** `https://saptha-event-portal-production.up.railway.app/`

| Role | Email | Password |
|---|---|---|
| Student | `student@demo.com` | `Demo1234` |
| Club SPOC | `spoc@demo.com` | `Demo1234` |
| Judge | `judge@demo.com` | `Demo1234` |
| Coordinator | `coordinator@demo.com` | `Demo1234` |

---

## SapthaEvent LiveOS — The Flagship Feature Set

These three capabilities together are what no university event system has ever shipped:

### 1. Real-Time SSE Leaderboard
`GET /live/<event_id>` — project onto any screen during the event.

- **No WebSocket server** — pure Server-Sent Events, works through proxies and Railway's infra
- Reads `scores` sub-collection from Firestore, averages across all judges, sorts by score
- Pushes ranked update every 3 seconds; client auto-reconnects after 5-minute guard window
- **Podium view**: top-3 shown as gold/silver/bronze cards (CSS `order: 2,1,3`)
- Rank-change animation: rows flash green (↑) or red (↓) on each tick
- Fullscreen toggle — optimised for projector display with dark theme (`#05050f`)
- Falls back to `/live/data/<event_id>` JSON snapshot for initial load

### 2. AI Event Report
`GET /spoc/ai_report/<event_id>` — one click after closing an event.

- Builds a stats payload: registrations, attendance %, judge count, avg/top score, podium
- Sends to **Gemini 2.5 Flash** with a structured prompt → 3-paragraph narrative debrief
- Falls back gracefully to a data-driven paragraph if no API key or network failure
- Full leaderboard table with score bars rendered inline
- `@media print` CSS — prints/saves as clean PDF directly from browser

### 3. Achievement & XP Engine
Triggered automatically when a SPOC ends an event.

- Rank 1 → 🥇 **Champion** + 500 XP
- Rank 2 → 🥈 **Runner-Up** + 300 XP
- Rank 3 → 🥉 **Third Place** + 200 XP
- All scored participants → ⭐ **Participant** + 50 XP
- XP and badges accumulate across events — participants see a live badge wall on their dashboard
- Duplicate prevention: badges are deduped by label before writing to Firestore

---

## Portal Sections

### Participant Dashboard
- Register for events (custom form per event, team + solo support)
- Pay via Razorpay (webhook + HMAC verification)
- Track registration status, payment receipt, ticket QR code
- View accumulated XP and badge wall across all events

### Club SPOC Dashboard
- Create and manage events with AI-generated form schemas (Gemini)
- Set registration caps, deadlines, team sizes, payment amounts
- Live Board button → opens SSE leaderboard in new tab
- AI Report button → generates post-event debrief
- Blast Email → send custom email to all/attended/winners with one form
- Clone Event → duplicate event doc + form schema, clear dates
- Export attendee CSV (name, USN, phone, score, attendance)
- QR-code scanner for attendance marking

### Judge Interface
- Assigned to specific events by admin
- Score individual teams with per-criterion rubric
- Scores averaged server-side — no manual collation
- View current leaderboard snapshot

### Coordinator Tools
- Cross-event attendance dashboard
- QR scanner (camera or manual entry) for entry gate
- Event lifecycle controls (open/close registration, end event)

### Admin Panel
- Create users (SPOC, Judge, Coordinator, Admin) with auto-generated passwords
- Bulk-assign judges to events
- System-wide audit log (`actions` Firestore collection)
- Email diagnostic endpoint (`/diag/email` — SuperAdmin only)

---

## Automated Email Engine

All email is non-blocking — queued to Celery workers.

| Trigger | What sends | When |
|---|---|---|
| Registration | Confirmation + ticket PDF | Immediately |
| Payment | Receipt with amount | On Razorpay webhook |
| 3-day reminder | "Event in 3 days" | 09:00 IST, automated |
| 24-hour reminder | "Tomorrow! Here's your ticket" | 09:00 IST, automated |
| Velocity alert | SPOC notified if fill rate < 70% with 3 days to deadline | 09:45 IST, automated |
| Password reset | Timed token link (1-hour TTL) | On request |
| Blast email | Custom SPOC-authored message | On demand |

Providers: **Resend** (primary) or **Gmail SMTP** (fallback) — auto-detected from env vars.

---

## Payments

- Razorpay order created server-side at registration
- Client completes payment in Razorpay modal
- Server verifies `razorpay_signature` with HMAC-SHA256 before writing `payment_status: paid`
- No client-side trust — amount and order_id are always fetched from Firestore

---

## Scheduled Tasks (Celery Beat)

```
09:00 IST  send_3day_reminders       — email participants 3 days before event
09:00 IST  send_24h_reminders        — email participants 24h before event
09:45 IST  check_registration_velocity — alert SPOC if fill < 70% with 3 days to deadline
00:00 IST  auto_close_registrations  — close regs past deadline
00:00 IST  archive_past_events       — move ended events to archive
```

Dev mode uses APScheduler (in-process) so no Redis/worker needed locally.  
Production uses `celery -A celery_app worker` + `celery -A celery_app beat`.

---

## Architecture

```
Browser ──HTTPS──▶ Railway (Gunicorn 4 workers)
                        │
                   Flask App
                   ├── routes_auth.py        Login / Register / Password Reset
                   ├── routes_participant.py  Student dashboard, registration, payment
                   ├── routes_spoc.py         SPOC dashboard, AI report, blast, clone
                   ├── routes_judge.py        Scoring interface
                   ├── routes_coordinator.py  Attendance, scanner
                   ├── routes_admin.py        User management, audit log
                   ├── routes_live.py         SSE leaderboard stream
                   ├── routes_forms.py        AI form schema generation
                   ├── routes_public.py       Home, event listings
                   └── routes_ticket.py       QR ticket + PDF
                        │
          ┌─────────────┼────────────────┐
          ▼             ▼                ▼
    Firestore       Celery Worker    Razorpay API
    (NoSQL)         + Beat           (Payments)
                        │
                      Redis
                   (broker/result)
                        │
                   Gemini 2.5 Flash
                   (AI reports, forms)
                        │
                   Resend / Gmail SMTP
                   (Transactional email)
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
| Task queue | Celery 5 + Redis |
| AI / LLM | Google Gemini 2.5 Flash |
| Payments | Razorpay |
| Email | Resend API / Gmail SMTP |
| Auth tokens | itsdangerous URLSafeTimedSerializer |
| Password hashing | Werkzeug scrypt |
| CSRF | Flask-WTF |
| Frontend | Bootstrap 5 + Jinja2 + Vanilla JS |
| QR codes | qrcode[pil] |
| PDF generation | ReportLab |
| Deployment | Railway (web + worker + beat) |
| CI | GitHub Actions (ruff lint + bandit security scan) |

---

## Project Structure

```
Event_Portel/
├── app.py                          # App factory, blueprint registration, CSRF, Razorpay
├── models.py                       # Firestore client init
├── celery_app.py                   # Celery config + Beat schedule
├── scheduler.py                    # APScheduler (dev mode)
├── utils.py                        # log_action, helpers
├── utils_email.py                  # Resend/Gmail send logic
│
├── routes_auth.py                  # Login, register, password reset, logout
├── routes_participant.py           # Student dashboard, registration, payment webhook
├── routes_spoc.py                  # SPOC dashboard, scan, AI report, blast, clone, achievements
├── routes_judge.py                 # Scoring interface
├── routes_coordinator.py           # Attendance, scanner
├── routes_admin.py                 # User/event management, audit log
├── routes_live.py                  # SSE leaderboard stream + projector page
├── routes_forms.py                 # AI form schema generation (Gemini)
├── routes_public.py                # Home, event listings, search/filter
├── routes_ticket.py                # QR ticket + PDF
│
├── tasks/
│   └── scheduled_tasks.py          # Celery tasks (reminders, velocity alert, lifecycle)
│
├── templates/
│   ├── live/leaderboard.html       # SSE projector page (dark theme, podium, rank animation)
│   ├── spoc/
│   │   ├── dashboard.html          # SPOC event management hub
│   │   ├── ai_report.html          # AI post-event report + print/PDF
│   │   └── scan.html               # QR attendance scanner
│   ├── participant/
│   │   ├── dashboard.html          # XP pill, badge wall, ticket list
│   │   └── ticket.html             # QR ticket view
│   ├── coordinator/scan.html
│   ├── admin/, judge/, public/
│   └── login.html, register.html, forgot_password.html, reset_password*.html
│
├── static/                         # CSS, JS, images
├── .github/workflows/ci.yml        # Ruff + Bandit CI
├── requirements.txt
├── Procfile                        # Railway: web + worker + beat
└── railway.toml
```

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/kirancodes-dev/saptha-event-portal.git
cd saptha-event-portal

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill environment variables
cp .env.example .env
# Edit .env — see table below

# 4. Run dev server (APScheduler runs in-process, no Redis needed)
python app.py

# 5. Production: separate worker + beat
gunicorn app:app --workers 4 --bind 0.0.0.0:8000
celery -A celery_app worker --loglevel=info
celery -A celery_app beat --loglevel=info
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret |
| `MASTER_SECRET_KEY` | Yes (prod) | SuperAdmin login gate |
| `SUPER_ADMIN_EMAIL` | Yes | First-boot superadmin email |
| `SUPER_ADMIN_DEFAULT_PASS` | Yes | First-boot superadmin password |
| `FIREBASE_CREDENTIALS` | Yes | JSON string of Firebase service account |
| `CELERY_BROKER_URL` | Prod | Redis URL (e.g. `redis://localhost:6379/0`) |
| `RESEND_API_KEY` | Email | Resend API key (preferred) |
| `MAIL_USER` | Email | Gmail address (fallback) |
| `MAIL_PASS` | Email | Gmail 16-char App Password |
| `MAIL_FROM` | Email | Sender address / display name |
| `RAZORPAY_KEY_ID` | Payments | Razorpay public key |
| `RAZORPAY_KEY_SECRET` | Payments | Razorpay secret (server-side only) |
| `GEMINI_API_KEY` | AI | Google Gemini API key |
| `FLASK_ENV` | Prod | Set to `production` to enforce master key |

---

## Role System

| Role | Login selector | Dashboard |
|---|---|---|
| `Student` | Student | `/participant/dashboard` |
| `ClubSPOC` | Club SPOC | `/spoc/dashboard` |
| `Judge` | Judge | `/judge/dashboard` |
| `Coordinator` | Coordinator | `/coordinator/dashboard` |
| `EventCoordinator` | Coordinator | `/coordinator/scanner` |
| `Admin` | Admin | `/admin/dashboard` |
| `SuperAdmin` | Super Admin | `/admin/dashboard` |

SuperAdmin login requires the master key in production. Cannot reset via email — by design.

---

## Security

- All passwords hashed with `scrypt` via Werkzeug — legacy plaintext rows blocked at login
- CSRF protection on all HTML form endpoints (Flask-WTF)
- Password reset via timed, signed token (1-hour TTL, `itsdangerous`)
- Razorpay payment amounts verified server-side via HMAC-SHA256
- SuperAdmin cannot be reset via email
- Session is permanent with server-controlled lifetime
- Ruff (linter) + Bandit (security scanner) run on every push via GitHub Actions

---

## CI/CD

- **GitHub Actions**: `ruff check` + `bandit -r .` on every push and PR
- **Railway**: auto-deploys on push to `main` — three services: web, worker, beat
- **Procfile**:
  ```
  web: gunicorn app:app --workers 4 --bind 0.0.0.0:$PORT
  worker: celery -A celery_app worker --loglevel=info
  beat: celery -A celery_app beat --loglevel=info
  ```

---

## Repository

**GitHub:** `https://github.com/kirancodes-dev/saptha-event-portal`  
**Live:** `https://saptha-event-portal-production.up.railway.app/`  
**University:** Sapthagiri NPS University, Bengaluru

---

<div align="center">
Built with Flask · Firestore · Celery · Gemini · Razorpay · Railway<br>
<sub>SapthaEvent — because spreadsheets don't belong at hackathons.</sub>
</div>
