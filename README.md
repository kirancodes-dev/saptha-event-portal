<div align="center">

<img src="static/img/hero-banner.webp" width="820" alt="SapthaEvent — the event portal of Sapthagiri NPS University" />

# SapthaEvent

### Every campus event. One place to join in.

**The official event portal of Sapthagiri NPS University, Bengaluru**

[![Python](https://img.shields.io/badge/Python-3.11-00185e?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3-00185e?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Database](https://img.shields.io/badge/PostgreSQL_·_SQLite-SQLAlchemy-00185e?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.sqlalchemy.org)
[![Charts](https://img.shields.io/badge/Apache_ECharts-5.5-c69d67?style=for-the-badge&logo=apacheecharts&logoColor=white)](https://echarts.apache.org)
[![Tests](https://img.shields.io/badge/pytest-893_passing-c69d67?style=for-the-badge&logo=pytest&logoColor=white)](#tests-and-quality)

</div>

---

## Why we built it

A university is full of things worth showing up for: a hackathon in the CSE block, a dance
championship in the main auditorium, a cricket final on the main ground, a guest lecture that
changes someone's mind about their career. Too often they reach students as a forwarded poster,
a Google Form and a spreadsheet that one tired organiser has to reconcile by hand.

SapthaEvent puts all of it in one place. Students find events and register in a minute, then walk
in with a QR ticket. Organisers create any kind of event (from a one-hour seminar to a multi-day fest with
its own sub-events), see who is coming, run check-in, judging and results, and issue certificates
that anyone can verify. The university sees everything that happens on campus, with the numbers to
back it up.

It was built for the people who make campus life happen, the students, the club leads and the faculty
who give up their evenings for it, and we hope it makes their work a little lighter.

---

## What each person can do

| Role | What they get |
|:--|:--|
| **Visitor** | The home page with the next events live from the database, filters and search, event pages, the university's schools and official accounts, certificate verification. |
| **Student** | Register (solo or as a team) for free and paid events, QR tickets, a dashboard of upcoming events, results, certificates and feedback, in-app notifications. |
| **Club SPOC** | A 7-step event wizard for **27 kinds of event** in 8 groups, drafts and a review page before publishing, fests with sub-events, a form builder, staff and rooms, results and certificates, and analytics for their own events. |
| **Event coordinator** | Registrations and exports, the QR check-in scanner, rooms, rounds and publishing results for the events they run. |
| **Judge** | The teams to score against the event's criteria, and the live leaderboard. |
| **Volunteer** | The check-in scanner on the event day. |
| **Super Admin** | Everything: all events (approve, change status, hand to another SPOC), users and roles, registrations across events, analytics across the university, venues and rooms, payments and refunds, announcements, system status and the audit log. |

---

## Highlights

- **Every kind of event, one wizard.** Talks, competitions, cultural, sports, community, career, fests and
  custom events, each with its own details (the sport and format for a tournament, the speaker for a
  seminar, the company for a placement drive). Fees per participant group, team sizes, judging criteria,
  prizes, sponsors and room booking with clash checks. Every event starts as a draft and is reviewed
  before it goes live.
- **Registration that just works.** A form per event (or the standard one), team members with their own
  details, waitlists, Razorpay payments with coupons and refunds, and a QR ticket the moment you register.
- **Event day.** QR check-in at the gate, live attendance, rooms and rounds, judges' scoring against the
  rubric and **one leaderboard** shared by the projector board, the live board, the judges, the results
  page and the published winners (equal scores share a place).
- **Certificates you can trust.** Issued to everyone who attended, each with a verification link and QR code.
- **Analytics.** Apache ECharts with filters for period and category: compare every event side by side
  (choose the measures, sort, top N or all, a breakdown that adds up), registrations over time, a weekday ×
  hour heatmap, the registration-to-certificate funnel, revenue and no-shows. Every chart has a table
  view and a PNG download, and the colours are checked for colour-blind readers in light and dark mode.
- **Notifications.** Email, WhatsApp and the in-app bell; announcements to any group.
- **For everyone.** Mobile-first layouts, dark mode, keyboard and screen-reader friendly, an installable PWA,
  and English, Hindi and Kannada.
- **Safe by default.** Server-side permissions on every route, CSRF protection, a strict Content Security
  Policy, rate-limited login, hashed passwords, refusal to start in production without real secrets, and
  seed scripts that refuse production databases.

---

## Run it locally

You need Python 3.11 and Git.

```bash
git clone https://github.com/kirancodes-dev/saptha-event-portal.git
cd saptha-event-portal
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python app.py                                          # http://127.0.0.1:5001
```

With no `DATABASE_URL`, data lives in `saptha_fallback.db` (SQLite, gitignored). Settings go in `.env`
(start from `.env.example`). In production (`FLASK_ENV=production`) the app refuses to start without
`DATABASE_URL` (or `CLOUD_SQL_INSTANCE`), `SECRET_KEY` and `MASTER_SECRET_KEY`.

### A full demo in one command

```bash
python seed_showcase.py
```

This empties the **local** database and builds a realistic university through the portal's own pages:

- 1 Super Admin, 3 Club SPOCs, 3 coordinators, 4 judges, a volunteer and 60 students across 9 programmes
- the main campus with 4 buildings and 13 rooms
- **40 upcoming events, two a day for the next 20 days**, of every kind, with registrations and QR tickets
- 8 events from the last two weeks with attendance, judges' scores, published results, certificates and feedback
- announcements in every student's notifications

Demo accounts use `@snpsu.test`, a reserved domain that never receives mail, so a demo can't write to a real
person. Passwords are printed once at the end of the run (or set `SEED_<ROLE>_PASSWORD` to choose them).
The script refuses anything that looks like a production database.

### With Docker (PostgreSQL, Redis, Celery)

```bash
cp .env.example .env           # set SECRET_KEY and MASTER_SECRET_KEY
docker compose up --build      # http://localhost:8080
docker compose exec web env SUPER_ADMIN_EMAIL=you@college.edu \
    SUPER_ADMIN_PASS='choose-a-Strong-pass1' python init_superadmin.py
```

---

## How it is built

| Layer | Technology |
|:--|:--|
| Web | Flask 3, Jinja templates, Bootstrap 5, a shared design system (`static/css/global.css`) |
| Data | SQLAlchemy models (`models_pg.py`) on PostgreSQL or SQLite, Alembic migrations, a document-style adapter (`db_adapter.py`) |
| Jobs | Celery with an outbox that retries anything that failed to send |
| Charts | Apache ECharts through `static/js/se-echarts.js` |
| Documents | ReportLab certificates with QR verification, Excel and PDF exports |
| Messages | Email (SMTP/Brevo), WhatsApp (Twilio), web push |
| AI | Google Gemini for the event writer, form generator and report summaries (optional) |
| Hosting | Docker, Google Cloud Run, PostgreSQL |

```
app.py                  the app, home page and public routes
routes_*.py             one blueprint per area (admin, spoc, coordinator, judge, participant, forms, …)
services_*.py           the rules: event types, workflow, permissions, payments, analytics, leaderboard, …
models_pg.py, db_*.py   the database
templates/, static/     pages, styles and scripts (no inline scripts: a strict CSP)
tests/                  pytest, against a temporary database
docs/                   deployment, API, architecture and the feature review
seed_showcase.py        the demo data
university_info.py      the university's details shown on the home page
```

---

## Tests and quality

```bash
python -m pytest        # uses a temporary database, never your local data
ruff check .
```

The suite has **914 tests**. In the full run of 13 October 2026, 893 pass (after one new test was made
independent of the order the tests run in) and 1 is skipped. The 20 that fail are known and tracked, not hidden:

- 19 are listed in UPG-62: two Stripe tests (Razorpay is the payment provider now), three for the matchmaker
  feature, twelve that check helper scripts the seed-safety guard doesn't cover yet, and two seminar
  lifecycle tests;
- 1, the event-status job test, fails only between midnight and 05:30 IST because the job uses UTC dates (UPG-90).

Planned work, what is done and what is open lives in [`docs/FEATURE_REVIEW.md`](docs/FEATURE_REVIEW.md);
deployment is in [`docs/DEPLOY.md`](docs/DEPLOY.md), and the API in [`docs/API.md`](docs/API.md).

---

## Thank you

To the students who tested every form, the club leads who told us what was missing, and the faculty who
believed a campus portal could be this good: this is yours.

---

## License

MIT License

Copyright (c) 2026 Sapthagiri NPS University

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

---

<div align="center">

<img src="static/img/snpsu-logo-reversed.png" width="220" alt="Sapthagiri NPS University" />

**Built with care, for everyone who makes campus life happen.**

Sapthagiri NPS University · Bengaluru · 2026

</div>
