# 🚀 SapthaEvent - University Event Portal

**Status:** ✅ Production Ready  
**Version:** 1.0.0  
**For Production Setup:** See [../PRODUCTION_README.md](../PRODUCTION_README.md)

A full-stack Event Management System built for Sapthagiri NPS University - now production-grade with comprehensive testing, security hardening, and enterprise-level features.

## 🌟 Key Features
- **Role-Based Access:** Separate dashboards for Students, Club SPOCs, Coordinators, and Judges.
- **Live Evaluation:** Judges can score teams in real-time with a digital scorecard.
- **Smart Attendance:** Coordinators can mark attendance, synced instantly to the backend.
- **AI Chatbot:** Built-in assistant to answer queries about event dates and contacts.
- **Automated Reports:** SPOCs can export participant data (Attendance + Scores) to CSV.

## 🛠️ Tech Stack
- **Backend:** Python (Flask)
- **Database:** Google Firebase Firestore (NoSQL)
- **Frontend:** Bootstrap 5, Jinja2, JavaScript
- **Deployment:** Docker, Gunicorn, Render

## 📂 Project Structure
```text
/sapthagiri_project
├── /templates         # HTML Files (Frontend)
├── /static            # CSS/Images
├── app.py             # Main Application Logic
├── models.py          # Database Connectivity
├── routes_spoc.py     # Logic for Club Leads
├── routes_judge.py    # Logic for Scoring
└── Dockerfile         # Deployment Configuration