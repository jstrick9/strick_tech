# ═══════════════════════════════════════════════════════════════
#  Agentic OS — Docker Image
#  One-command deployment: docker build -t agentic-os . && docker run -p 8787:8787 agentic-os
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim

# Metadata
LABEL maintainer="jstrick9"
LABEL description="Agentic OS — Local-first Agentic AI Operating System"
LABEL version="11.5.0"

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENTIC_OS_PORT=8787 \
    AGENTIC_OS_HOST=0.0.0.0

# Working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/memory /app/preview

# Expose port
EXPOSE 8787

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8787/api/system/stats || exit 1

# Run the application
CMD ["python", "run.py"]
