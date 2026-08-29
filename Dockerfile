# ═══════════════════════════════════════════════════════════════
#  Agentic OS — Docker Image (multi-stage, non-root)
#  Build: docker build -t agentic-os .
#  Run:   docker run -p 8787:8787 -v agentic-data:/app/data agentic-os
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: Install dependencies ──────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

# ── Stage 2: Production image ──────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="jstrick9"
LABEL description="Agentic OS — Local-first Agentic AI Operating System"
LABEL version="11.5.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENTIC_OS_PORT=8787 \
    AGENTIC_OS_HOST=0.0.0.0 \
    AGENTIC_OS_DATA_DIR=/app/data \
    PYTHONPATH=/app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r agentic && useradd -r -g agentic -d /app -s /sbin/nologin agentic

WORKDIR /app

# Copy dependencies from build stage
COPY --from=deps /build/deps /usr/local/lib/python3.12/site-packages/

# Copy application code
COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/build_bundle.py scripts/
COPY run.py pyproject.toml VERSION ./

# Rebuild and verify the frontend bundle INSIDE the image. Not optional.
#
# backend/app.py does not serve frontend/index.html as written -- it rewrites
# it to load content-hashed bundles from frontend/dist. `COPY frontend/` brings
# in whatever dist was on the builder's disk, so an image could serve stale
# JavaScript while every source file in it is current. That exact defect
# shipped from the macOS build path and cost five sessions to find.
#
# `--check` makes it a hard failure: a stale bundle fails the image build
# instead of becoming a running container that lies about its own version.
# Brotli is already in requirements.txt and present in the deps layer, so no
# extra install is needed -- adding one would break an offline/air-gapped build
# for no benefit.
RUN python scripts/build_bundle.py \
    && python scripts/build_bundle.py --check

# Create data directory with proper permissions
RUN mkdir -p /app/data/memory /app/data/preview \
    && chown -R agentic:agentic /app /app/data

USER agentic

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8787/api/health || exit 1

CMD ["python", "run.py"]
