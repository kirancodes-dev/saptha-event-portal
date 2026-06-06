<div align="center">

<img src="static/snpsu-logo.png" width="300" alt="Sapthagiri NPS University Logo" style="background: #1a2557; padding: 12px 24px; border-radius: 12px;" />

# ⚡ SapthaEvent
### **Enterprise Event Intelligence & Orchestration Platform**
**Sapthagiri NPS University, Bengaluru**

---

[![Live App](https://img.shields.io/badge/%F0%9F%8C%90%20Live%20Portal-saptha--event--portal-1a2557?style=for-the-badge&logo=google-cloud&logoColor=white)](https://saptha-event-portal-762269836348.us-east4.run.app/)
[![Python](https://img.shields.io/badge/Python-3.12-c9a45e?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Firebase](https://img.shields.io/badge/Firestore-NoSQL-FF6F00?style=for-the-badge&logo=firebase&logoColor=white)](https://firebase.google.com)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?style=for-the-badge&logo=google-gemini&logoColor=white)](https://ai.google.dev)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/kirancodes-dev/saptha-event-portal/ci.yml?branch=main&style=for-the-badge&label=Build%20Status)](https://github.com/kirancodes-dev/saptha-event-portal/actions)

<br/>

> **[🚀 Access the Live Production Portal](https://saptha-event-portal-762269836348.us-east4.run.app/)**  
> *Built for scale, speed, and real-time projector delivery. Say goodbye to spreadsheets.*

</div>

---

## 🌟 Why SapthaEvent?

Typical university events rely on fragmented Google Forms, manual scoring sheets, and delayed announcements. SapthaEvent bridges this gap with a **unified event intelligence engine**:

| The Old Way | The SapthaEvent Way |
| :--- | :--- |
| **Google Forms & Sheets** | Per-event dynamic JSON form schemas, automated team limits, and secure transactions. |
| **Manual Rubric Calculations** | Real-time digital scorecards, auto-averaged and normalized across multiple judges. |
| **Static Announcements** | Live Server-Sent Events (SSE) projector boards pushing rankings instantly. |
| **No Post-Event Action** | AI-generated executive summaries (via Gemini 2.5 Flash) with A4 PDF export capabilities. |
| **Invisible Achievements** | Deduplicated profile portfolios, XP point rewards, and earned badge assets. |
| **Fragmented Emails** | Brevo HTTP queue manager sending confirmations, dynamic tickets, and SPOC broadcast blasts. |

---

## 🔑 Demo Account Sandbox

Test the system instantly across different system roles on our **[Live Sandbox](https://saptha-event-portal-762269836348.us-east4.run.app/login)**:

| System Portal | Role | Credentials |
| :--- | :--- | :--- |
| **Student Dashboard** | Participant | `student@demo.com` &bull; `Demo1234` |
| **Club HQ** | Club SPOC | `spoc@demo.com` &bull; `Demo1234` |
| **Judge panel** | Evaluator | `judge@demo.com` &bull; `Demo1234` |
| **Gate Operations** | Coordinator | `coordinator@demo.com` &bull; `Demo1234` |

---

## ✨ Flagship Systems

### 1. 📺 Real-Time Projector Leaderboard (`/live/<event_id>`)
Optimized for high-visibility fullscreen projector displays at venues.
* **Pure Server-Sent Events (SSE)**: Pushes structured rank updates every 3 seconds without persistent WebSocket overhead.
* **Animated Ranks**: Highlights row changes dynamically with visual cues (green flash on rise ↑, red flash on drop ↓).
* **Podium Visualization**: The top 3 finalists are highlighted in gold, silver, and bronze containers with live scoring metrics.

### 2. 🤖 Gemini-Powered Post-Event Reports
Gathers event statistics, attendance rates, scoring distributions, and leaderboard podiums to generate an institutional report.
* **One-Click Generation**: SPOCs click a button to query Gemini 2.5 Flash.
* **Structured Format**: Produces executive analysis, participation statistics, and operational recommendations.
* **Print Optimization**: Integrates `@media print` CSS configurations to print or export directly as a standard A4 PDF document.

### 3. 🛡️ Public Certificate Verification Engine (`/verify/<cert_hash>`)
A professional verification page with interactive canvas-confetti, download triggers, status trackers, and sharing tools.
* **Cryptographic Verification**: Validates certificate validity via cryptographic document hashes.
* **Interactive Confetti**: Fuses canvas-confetti animations to celebrate verification.
* **Responsive Preview**: Embeds a scaled HTML certificate viewer using relative viewport sizes.
* **Action Center**:
  - Download PDF certificate (dynamic generation via ReportLab)
  - Direct LinkedIn & X sharing triggers
  - Copy-to-clipboard verification URL actions
  - Chronological event timeline (Generated &rarr; Delivered &rarr; Verified)

---

## 🏗 System Architecture

```
                       ┌──────────────────────────────┐
                       │   Client (Browser/Mobile)    │
                       └──────────────┬───────────────┘
                                      │ HTTPS
                                      ▼
                       ┌──────────────────────────────┐
                       │      Flask Web Service       │
                       └──────────────┬───────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│ Firestore Database│       │  Celery Task Bus  │       │  Razorpay Gateway │
│      (NoSQL)      │       │ (Redis Broker)    │       │ (Secure Payments) │
└───────────────────┘       └─────────┬─────────┘       └───────────────────┘
                                      │
                              ┌───────┴───────┐
                              ▼               ▼
                        ┌───────────┐   ┌───────────┐
                        │ Gemini AI │   │ Brevo API │
                        │ (Reports) │   │  (Email)  │
                        └───────────┘   └───────────┘
```

---

## 🔧 Technical Stack

* **Core Backend**: Flask 3.x (Python 3.12)
* **Production Server**: Gunicorn
* **NoSQL Database**: Google Cloud Firestore
* **Task Pipeline**: Celery 5 (backed by Redis in Production, APScheduler fallback in Dev)
* **AI Engine**: Google Gemini 2.5 Flash API
* **Email Broker**: Brevo HTTP Client (resilient to SMTP port blocks)
* **Cryptographics**: `itsdangerous` Serializers & Werkzeug `scrypt` hashing
* **Document Services**: ReportLab PDF Engine & PyQRCode
* **Frontend Design**: Unified CSS Variables Theme, Bootstrap 5, FontAwesome 6, and Vanilla JS

---

## 🚀 Local Installation & Setup

### 1. Clone & Setup Environment
```bash
git clone https://github.com/kirancodes-dev/saptha-event-portal.git
cd saptha-event-portal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your local developer configurations:
```bash
cp .env.example .env
```
Ensure these values are configured:
```env
SECRET_KEY=generate-a-secure-random-key
SUPER_ADMIN_EMAIL=admin@snpsu.edu.in
SUPER_ADMIN_PASS=Saptha@Admin2026
MASTER_SECRET_KEY=SAPTHA@2026
BASE_URL=http://127.0.0.1:5001
GEMINI_API_KEY=your-gemini-api-key
BREVO_API_KEY=your-brevo-api-key
```

### 3. Setup Database Credentials
Drop your Google Cloud / Firebase service account credentials file as `serviceAccountKey.json` into the root directory.

### 4. Initialize Database & Seed
Initialize the default Super Admin credential record in Firestore:
```bash
python fix_superadmin.py
```

### 5. Start the Development Server
```bash
python app.py
```
Open **`http://127.0.0.1:5001`** in your browser.

---

## 👥 Access Control Matrix

The platform supports 6 distinct roles dynamically checked via route decorators:

| User Role | UI Dashboard URL | Core Capabilities |
| :--- | :--- | :--- |
| **Student** | `/participant/dashboard` | View portfolio, register for events, complete Razorpay payments, download tickets. |
| **Club SPOC** | `/spoc/dashboard` | Create events, configure dynamic registration fields, manage staff, open SSE scoreboard, generate AI reports. |
| **Judge** | `/judge/dashboard` | Evaluate participant teams, submit scores according to scoring rubrics. |
| **Coordinator** | `/coordinator/dashboard` | Scan check-in tickets, audit attendance registers system-wide. |
| **Admin** | `/admin/dashboard` | System diagnostics, user creation, judge allocation. |
| **Super Admin** | `/admin/dashboard` | Complete platform access override (requires the master secret key to authenticate). |

---

## ⚙️ CI/CD & Security Auditing
* **Linting & Code Quality**: Enforced via `ruff check` on all code paths.
* **Security Scanning**: Conducted on every commit using the `bandit` security analysis tool.
* **Automated Builds**: Verified with `pytest` unit test suites running in GitHub Actions.
* **Deployments**: Triggered automatically on pushes to the default branch to Google Cloud Run and Railway.

---

<div align="center">

&copy; 2026 Sapthagiri NPS University, Bengaluru &bull; Developed by SapthaEvent Platform Team

**SapthaEvent — Spreadsheets don't belong at hackathons.**

</div>
