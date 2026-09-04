#!/bin/bash
set -e

# Wait for PostgreSQL if DATABASE_URL is set and points to postgres
if [ -n "${DATABASE_URL}" ] && echo "${DATABASE_URL}" | grep -q "postgres"; then
    echo "Waiting for database..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if python -c "
import socket, sys
from urllib.parse import urlparse
url = urlparse('${DATABASE_URL}')
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect((url.hostname or 'localhost', url.port or 5432))
s.close()
" 2>/dev/null; then
            echo "Database is ready."
            break
        fi
        attempt=$((attempt + 1))
        echo "  attempt $attempt/$max_attempts - database not ready, retrying..."
        sleep 2
    done
    if [ $attempt -eq $max_attempts ]; then
        echo "WARNING: Could not connect to database after $max_attempts attempts, starting anyway..."
    fi
fi

# Create data directories if they don't exist
mkdir -p /app/data/artifacts /app/data/brain

# Run migrations if any exist (placeholder)
# if [ -f "/app/src/core/db/migrate.py" ]; then
#     echo "Running database migrations..."
#     python -m src.core.db.migrate
# fi

exec "$@"
