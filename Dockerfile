# =========================================================
# Saptha Event Portal - Production Dockerfile for GCP Cloud Run
# =========================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production

WORKDIR /app

# Install system runtime & build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --retries 10 --timeout 60 -r requirements.txt

# Copy application source code
COPY . .

# Expose port (Cloud Run sets PORT automatically to 8080)
EXPOSE 8080

# Start Gunicorn server using production gunicorn.conf.py configuration
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
