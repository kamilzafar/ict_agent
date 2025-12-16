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
# ChromaDB and other libraries may need these at runtime
# gosu is needed for clean user switching in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

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
COPY app.py ./
COPY core/ ./core/
COPY tools/ ./tools/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Copy and set up entrypoint script (before switching users)
COPY docker/entrypoint.sh /entrypoint.sh

# Create necessary directories first with proper permissions
RUN mkdir -p /app/memory_db /app/sheets_index_db /app/logs /app/credentials && \
    chmod 755 /app/memory_db /app/sheets_index_db /app/logs /app/credentials && \
    chmod +x /entrypoint.sh

# Create cache directory for uv with proper permissions
RUN mkdir -p /home/appuser/.cache/uv && \
    chown -R appuser:appuser /home/appuser

# Credentials are not baked into the image for security.
# Mount them at runtime (e.g., docker-compose volume) to /app/credentials/google-sheets-service-account.json
# Set ownership and permissions for app directories and entrypoint
RUN chown -R appuser:appuser /app /entrypoint.sh && \
    chmod -R 755 /app/memory_db /app/sheets_index_db /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    UV_CACHE_DIR=/home/appuser/.cache/uv

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
