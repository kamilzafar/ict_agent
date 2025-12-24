#!/bin/bash
# Entrypoint script to ensure proper permissions and handle multi-worker startup

set -e

# Get the UID and GID of appuser (created in Dockerfile)
APPUSER_UID=$(id -u appuser 2>/dev/null || echo "1000")
APPUSER_GID=$(id -g appuser 2>/dev/null || echo "1000")

# Ensure directories exist (both in container and for mounted volumes)
mkdir -p /app/memory_db /app/logs 2>/dev/null || true

# Fix permissions on mounted volumes (if running as root)
if [ "$(id -u)" = "0" ]; then
    # Fix ownership of mounted directories
    # Try to chown the directories - this will work for contents even if mount points can't be changed
    chown -R ${APPUSER_UID}:${APPUSER_GID} /app/memory_db /app/logs 2>/dev/null || true
    # Ensure directories are writable
    chmod -R 755 /app/memory_db /app/logs 2>/dev/null || true
    
    # Switch to appuser and execute the command
    exec gosu appuser "$@"
else
    # Already running as appuser, just execute
    exec "$@"
fi

