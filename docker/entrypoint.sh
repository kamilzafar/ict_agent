#!/bin/bash
# Entrypoint script to ensure proper permissions and handle multi-worker startup

set -e

# Ensure directories exist (permissions are set in Dockerfile)
mkdir -p /app/memory_db /app/sheets_index_db /app/logs 2>/dev/null || true

# Execute the command
exec "$@"

