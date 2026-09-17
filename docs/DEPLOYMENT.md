# SapthaEvent Production Deployment Guide

## 1. Supported Deployment Targets
SapthaEvent is containerized and cloud-agnostic. It can be deployed on:
1. **Railway** (Procfile / Nixpacks / Dockerfile)
2. **Google Cloud Run** (Serverless container deployment)
3. **AWS ECS / DigitalOcean App Platform** (Docker container)
4. **Self-Hosted Linux VM** (Systemd + Nginx reverse proxy + Gunicorn)

---

## 2. Environment Variables Configuration

Copy `.env.example` to `.env` and configure production secrets:

```bash
# ── Core Runtime ──
FLASK_ENV=production
SECRET_KEY=<generate_random_64_char_hex>
JWT_SECRET_KEY=<generate_random_64_char_hex>
MASTER_SECRET_KEY=<generate_secure_passphrase>
FORCE_HTTPS=true

# ── Port & Host ──
PORT=5001
BASE_URL=https://events.snpsu.edu.in

# ── Primary Relational Database (PostgreSQL / Cloud SQL) ──
DATABASE_URL=postgresql://saptha_admin:SecurePass@cloudsql-instance:5432/saptha_prod
USE_CLOUD_SQL_CONNECTOR=true
CLOUD_SQL_CONNECTION_NAME=snpsu-cloud:asia-south1:saptha-pg

# ── Firebase Admin SDK (Cloud Firestore & Auth) ──
FIREBASE_KEY_PATH=serviceAccountKey.json
# Or pass base64 encoded credential in cloud environments:
# FIREBASE_SERVICE_ACCOUNT_BASE64=eyJ...

# ── AI Services (Google Gemini) ──
GEMINI_API_KEY=AIzaSy...

# ── Redis / Celery (Optional Caching & Async Tasks) ──
REDIS_URL=redis://default:SecureRedis@redis-cluster:6379/0

# ── SuperAdmin Provisioning ──
SUPER_ADMIN_EMAIL=superadmin@snpsu.edu.in
SUPER_ADMIN_PASS=ChangeImmediatelyOnFirstLogin2026!
```

---

## 3. Containerization (Dockerfile)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential, libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5001/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--threads", "2", "--timeout", "120", "app:app"]
```

---

## 4. Health Checks & Observability
The platform exposes two standard observability endpoints for load balancers and orchestrators:
- `GET /health`: Liveness probe — verifies HTTP server responsiveness and memory limits. Returns `{"status": "healthy", "timestamp": "..."}`.
- `GET /health/ready`: Readiness probe — performs live query test against the primary database. Returns `200 OK` when ready to serve traffic, `503 Service Unavailable` if database connection fails.
