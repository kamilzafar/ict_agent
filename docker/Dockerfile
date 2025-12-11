FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY app.py ./
COPY core/ ./core/
COPY tools/ ./tools/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Expose port
EXPOSE 8009

# Run the application
CMD ["uv", "run", "python", "scripts/run_api.py"]

