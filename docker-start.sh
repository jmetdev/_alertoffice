#!/bin/sh
# Docker container startup script for alertOffice

set -e

echo "========================================"
echo "alertOffice Container Startup"
echo "========================================"
echo ""

# Show environment info
echo "Environment Information:"
echo "  Working Directory: $(pwd)"
echo "  Python Version: $(python --version)"
echo "  User: $(whoami)"
echo ""

# Validate required environment variables
echo "Validating environment variables..."
if [ -z "$APP_SECRET_KEY" ]; then
    echo "ERROR: APP_SECRET_KEY environment variable is required"
    exit 1
fi

if [ -z "$CUCM_HOST" ]; then
    echo "WARNING: CUCM_HOST not set. Device management features will be unavailable."
fi

if [ -z "$FREESWITCH_ESL_HOST" ]; then
    echo "WARNING: FREESWITCH_ESL_HOST not set. Conference monitoring will be unavailable."
fi

echo "✓ Environment validation complete"
echo ""

# Create directories if they don't exist
echo "Setting up directories..."
mkdir -p /app/data
mkdir -p /app/logs
mkdir -p /recordings
mkdir -p /logs

echo "✓ Directories ready"
echo ""

# Show volume mounts
echo "Volume Mounts:"
echo "  Data:       /app/data → /opt/alertoffice/data"
echo "  Logs:       /app/logs → /opt/alertoffice/logs"
echo "  Recordings: /recordings → /opt/alertoffice/recordings"
echo "  FS Logs:    /logs → /opt/freeswitch/logs (read-only)"
echo ""

# Check directory permissions
echo "Checking directory permissions..."
if [ -w /app/data ]; then
    echo "✓ /app/data is writable"
else
    echo "ERROR: /app/data is not writable"
    exit 1
fi

if [ -w /app/logs ]; then
    echo "✓ /app/logs is writable"
else
    echo "ERROR: /app/logs is not writable"
    exit 1
fi
echo ""

# Initialize database
echo "Initializing database..."
python -c "from sqlite_crud.database import initialize_database; initialize_database(); print('✓ Database initialized successfully')"
echo "  Database: /app/data/ucm_devices.db"
echo ""

# Show configuration
echo "Configuration:"
echo "  CUCM Host:      ${CUCM_HOST:-not configured}"
echo "  CUCM Version:   ${CUCM_VERSION:-11.5}"
echo "  FreeSWITCH ESL: ${FREESWITCH_ESL_HOST:-not configured}"
echo "  Redis Host:     ${REDIS_HOST:-localhost}"
echo ""

# Note about auto-sync
if [ -n "$CUCM_HOST" ] && [ -n "$CUCM_USERNAME" ] && [ -n "$CUCM_PASSWORD" ]; then
    echo "Note: If database is empty, devices will be automatically synced from CUCM on startup."
else
    echo "Note: CUCM credentials not fully configured. Device sync disabled."
fi
echo ""

# Start the Flask application
echo "========================================"
echo "Starting Flask Application"
echo "========================================"+++
echo ""

exec python -m flask run --host=0.0.0.0 --port=5000
