# ============================================================================
# Multi-stage Production Dockerfile
# Optimized for security, performance, and minimal image size
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies
# ----------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /build

# Install system dependencies required for building Python packages
# and runtime dependencies for ChromaDB and other libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
# Using --frozen to ensure reproducible builds
RUN uv sync --frozen --no-dev

# ----------------------------------------------------------------------------
# Stage 2: Runtime - Production image
# ----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Install minimal runtime dependencies
# ChromaDB, SQLite, and other libraries may need these at runtime
# gosu is needed for clean user switching in entrypoint
# locales is needed for UTF-8 support for multilingual content
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gosu \
    sqlite3 \
    libsqlite3-dev \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen en_US.UTF-8

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

WORKDIR /app

# Copy uv from builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application code
# Order matters: copy static files first, then code that changes frequently
# Config files (prompt.txt) are copied separately to ensure changes always trigger rebuild
COPY app.py ./
COPY core/ ./core/
COPY tools/ ./tools/
COPY scripts/ ./scripts/
COPY static/ ./static/
# Copy config last to ensure prompt.txt and other config changes always invalidate cache
COPY config/ ./config/

# Copy and set up entrypoint script (before switching users)
COPY docker/entrypoint.sh /entrypoint.sh

# Create necessary directories first with proper permissions
# memory_db contains: ChromaDB data, SQLite checkpoints.db, JSON metadata
RUN mkdir -p /app/memory_db /app/logs /app/static /app/credentials && \
    chmod 755 /app/memory_db /app/logs /app/static /app/credentials && \
    chmod +x /entrypoint.sh && \
    # Ensure SQLite can write to memory_db
    chmod 777 /app/memory_db

# Create cache directory for uv with proper permissions
RUN mkdir -p /home/appuser/.cache/uv && \
    chown -R appuser:appuser /home/appuser

# Set ownership and permissions for app directories and entrypoint
RUN chown -R appuser:appuser /app /entrypoint.sh && \
    chmod -R 755 /app/memory_db /app/logs

# Set environment variables for production
# UTF-8 locale settings for multilingual content support (Urdu, English, etc.)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    UV_CACHE_DIR=/home/appuser/.cache/uv \
    WORKERS=4 \
    MAX_CONCURRENT=100 \
    KEEP_ALIVE=120 \
    TIMEOUT=120 \
    BACKLOG=2048 \
    LOG_LEVEL=info \
    SUMMARIZE_INTERVAL=10 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PYTHONIOENCODING=utf-8

# Keep as root for entrypoint to fix permissions on mounted volumes
# Entrypoint will switch to appuser after fixing permissions
USER root

# Expose port
EXPOSE 8009

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

# Labels for metadata
LABEL maintainer="ICT Agent Team" \
      version="0.1.0" \
      description="Intelligent Chat Agent with Long-Term Memory" \
      org.opencontainers.image.title="ICT Agent" \
      org.opencontainers.image.description="Production-ready intelligent chat agent API" \
      org.opencontainers.image.version="0.1.0"

# Run the application
CMD ["uv", "run", "python", "scripts/run_api.py"]
