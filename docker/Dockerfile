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
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

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

# Create necessary directories first
RUN mkdir -p /app/memory_db /app/sheets_index_db /app/logs /app/credentials

# Copy credentials - required for Google Sheets API
# Copy credential.json from project root (required for deployment)
COPY credential.json ./

# Copy credentials directory if it exists (for additional credential files)
# Note: This will fail if credentials/ doesn't exist, but that's okay - it's optional
# If you have a credentials/ directory, uncomment the line below:
# COPY credentials/ ./credentials/

# Organize credentials: ensure credential.json is available in credentials directory
# This copies the root credential.json to the credentials directory where the app expects it
RUN if [ -f credential.json ]; then \
        # Copy to the expected location for Google Sheets service account
        cp credential.json /app/credentials/google-sheets-service-account.json || true; \
        # Also keep a copy with original name for backward compatibility
        cp credential.json /app/credentials/credential.json || true; \
    fi && \
    # Ensure credentials directory exists and has proper permissions
    mkdir -p /app/credentials && \
    chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8009

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
