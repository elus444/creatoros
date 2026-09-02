# Dockerfile for FastAPI backend.
# Build context is this "backend" directory (docker-compose.yml: build: ./backend;
# on Railway: service Root Directory = "backend"). All COPY paths below are
# relative to that context — do not prefix them with "backend/".
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Create non-root user
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check (uses stdlib only — "requests" is not a project dependency).
# Binds to whatever port the process actually listens on (PORT if set).
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD sh -c 'python -c "import urllib.request as u; u.urlopen(\"http://localhost:${PORT:-8000}/api/v1/health\", timeout=5)"'

# Run migrations then start. $PORT is injected by the platform (e.g. Railway);
# defaults to 8000 for local/docker-compose use.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
