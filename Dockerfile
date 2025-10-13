# Dockerfile for deploying the Slack Thread Analyzer Bot on AWS
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies
COPY requirements-new.txt ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements-new.txt

# Copy the application code
COPY . .

# AWS injects PORT; default to 3000 for local runs
ENV PORT=3000

# Use uvicorn to serve the FastAPI app
CMD ["sh", "-c", "uvicorn run:app --host 0.0.0.0 --port ${PORT:-3000} --workers ${WEB_CONCURRENCY:-1}"]
