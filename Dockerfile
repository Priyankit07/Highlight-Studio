# ==========================================
# Stage 1: Build Frontend Assets
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Python Backend Runtime
# ==========================================
FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Deno for yt-dlp JavaScript challenge solving
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /bin/uv

WORKDIR /app

# Install Python dependencies first for caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application source and assets (never copy raw videos, output video, audio output, data/, .env or cookies)
COPY codebase/ ./codebase/
COPY api/ ./api/
COPY tools/ ./tools/
COPY README.md ./

# Copy compiled frontend build into frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Generate demo sample during image build into /app/demo_assets/ (NOT into /app/data)
RUN mkdir -p /app/demo_assets && \
    uv run python tools/make_synthetic_match.py --duration 120 --out-dir /app/demo_assets && \
    cp /app/demo_assets/synthetic_match.mp4 /app/demo_assets/source.mp4 && \
    uv run python -c "from tools.seed_demo_job import setup_demo_job; setup_demo_job(target_override='/app/demo_assets')"

# Create persistent data directory mount point
RUN mkdir -p /app/data

# Environment defaults (mode defaults for MAX_UPLOAD_GB, RETENTION_DAYS, etc. are handled dynamically by APP_ENV)
ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    MAX_CONCURRENT_JOBS=1

EXPOSE 8000

VOLUME ["/app/data"]

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
