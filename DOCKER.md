# Docker Deployment Guide

## Overview

This guide covers deploying alertOffice using Docker and Docker Compose with volume mappings to `/opt/alertoffice/` for persistent data.

## Architecture

```
Host System                          Docker Container
─────────────────────────────────── ───────────────────────────
/opt/alertoffice/data            →  /app/data (SQLite DB)
/opt/alertoffice/logs            →  /app/logs (App logs)
/opt/alertoffice/recordings      →  /recordings (Call recordings)
/opt/freeswitch/logs             →  /logs (FreeSWITCH logs, RO)

Port 5000                        →  Container port 5000 (Flask)
Port 6379                        →  Redis
```

## Prerequisites

### Required

- **Docker Engine** 20.10+ ([Install Docker](https://docs.docker.com/get-docker/))
- **Docker Compose** 2.0+ ([Install Compose](https://docs.docker.com/compose/install/))
- **Root/sudo access** for creating directories in `/opt/`

### System Requirements

- **CPU**: 2+ cores recommended
- **RAM**: 2GB minimum, 4GB recommended
- **Disk**: 10GB+ free space (depends on number of devices and logs)

## Quick Start

### 1. Create Host Directories

```bash
# Create alertOffice directories
sudo mkdir -p /opt/alertoffice/{data,logs,recordings}

# Create FreeSWITCH logs directory (if you have FreeSWITCH)
sudo mkdir -p /opt/freeswitch/logs

# Set ownership (replace with your user)
sudo chown -R $USER:$USER /opt/alertoffice
sudo chown -R $USER:$USER /opt/freeswitch/logs
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required Variables:**
```bash
APP_SECRET_KEY=your-secret-key-here
CUCM_HOST=your-cucm-host
CUCM_USERNAME=your-cucm-user
CUCM_PASSWORD=your-cucm-password
FREESWITCH_ESL_HOST=your-freeswitch-host
FREESWITCH_ESL_PASSWORD=your-esl-password
PHONE_HTTP_USERNAME=your-phone-user
PHONE_HTTP_PASSWORD=your-phone-password
```

**Generate Secret Key:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Build and Start

```bash
# Build the Docker image
docker-compose build

# Start services in background
docker-compose up -d

# View logs (Ctrl+C to exit)
docker-compose logs -f
```

### 4. Access Application

Open your browser to: **http://localhost:5000**

### 5. Verify

```bash
# Check service status
docker-compose ps

# Check health
docker inspect alertoffice --format='{{.State.Health.Status}}'

# View recent logs
docker-compose logs --tail=50
```

## Volume Mappings

### Application Data (`/opt/alertoffice/data`)

**Contains:**
- `ucm_devices.db` - SQLite database with device information and phone groups

**Permissions:**
- Must be writable by container user
- Automatically created if missing
- Persists across container restarts

**Backup:**
```bash
sudo cp /opt/alertoffice/data/ucm_devices.db \
        /opt/alertoffice/data/ucm_devices.db.backup
```

### Application Logs (`/opt/alertoffice/logs`)

**Contains:**
- `alertoffice.log` - Current log file (rotates at 10MB)
- `alertoffice.log.*.zip` - Compressed rotated logs (30 days retention)

**Rotation:**
- Size: 10 MB per file
- Retention: 30 days
- Compression: gzip

**Monitor:**
```bash
# Follow logs in real-time
tail -f /opt/alertoffice/logs/alertoffice.log

# View last 100 lines
tail -n 100 /opt/alertoffice/logs/alertoffice.log

# Search for errors
grep -i error /opt/alertoffice/logs/alertoffice.log
```

### Conference Recordings (`/opt/alertoffice/recordings`)

**Contains:**
- WAV audio files from FreeSWITCH conferences
- Filename format: `{conference}-{YYYYMMDD}-{HHMMSS}.wav`
- Example: `19001-20260202-163715.wav`

**Size Management:**
```bash
# Check total size
du -sh /opt/alertoffice/recordings

# Delete recordings older than 90 days
find /opt/alertoffice/recordings -type f -mtime +90 -delete

# Archive old recordings
tar czf recordings-$(date +%Y%m).tar.gz /opt/alertoffice/recordings/*.wav
```

### FreeSWITCH Logs (`/opt/freeswitch/logs`)

**Read-Only Mount:**
- Container has read-only access
- Must exist on host before starting container
- Typically managed by FreeSWITCH service

**Setup:**
```bash
# If FreeSWITCH is running, point to its log directory
sudo ln -s /var/log/freeswitch /opt/freeswitch/logs

# Or create a shared directory
sudo mkdir -p /opt/freeswitch/logs
# Configure FreeSWITCH to log here
```

## Docker Commands

### Building

```bash
# Build the image
docker-compose build

# Build without cache (force rebuild)
docker-compose build --no-cache

# Build specific service
docker-compose build alertoffice
```

### Starting/Stopping

```bash
# Start services (detached)
docker-compose up -d

# Start and view logs (Ctrl+C to stop viewing, containers keep running)
docker-compose up -d && docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes (CAUTION: deletes Redis data)
docker-compose down -v

# Restart services
docker-compose restart

# Restart specific service
docker-compose restart alertoffice

# Restart with rebuild
docker-compose up -d --build
```

### Logs and Monitoring

```bash
# Follow all logs
docker-compose logs -f

# Follow specific service
docker-compose logs -f alertoffice

# Last 100 lines
docker-compose logs --tail=100

# Check service status
docker-compose ps

# View resource usage
docker stats alertoffice alertoffice-redis
```

### Container Access

```bash
# Execute bash in container
docker-compose exec alertoffice sh

# Run Python commands
docker-compose exec alertoffice python -c "from sqlite_crud.ucm_devices import get_all_ucm_devices; print(len(get_all_ucm_devices()))"

# Check database
docker-compose exec alertoffice ls -lh /app/data/

# View application logs from container
docker-compose exec alertoffice tail -f /app/logs/alertoffice.log
```

## Configuration

### Environment Variables

All configuration is done via environment variables in `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_SECRET_KEY` | **Yes** | - | Flask session encryption key |
| `CUCM_HOST` | **Yes** | - | CUCM hostname/IP |
| `CUCM_USERNAME` | **Yes** | - | CUCM admin username |
| `CUCM_PASSWORD` | **Yes** | - | CUCM admin password |
| `CUCM_VERSION` | No | `11.5` | CUCM version (11.5, 12.0, 12.5) |
| `CUCM_VERIFY_SSL` | No | `false` | Verify CUCM SSL certificates |
| `FREESWITCH_ESL_HOST` | **Yes** | - | FreeSWITCH hostname/IP |
| `FREESWITCH_ESL_PASSWORD` | **Yes** | - | ESL password |
| `FREESWITCH_ESL_PORT` | No | `8021` | ESL port |
| `PHONE_HTTP_USERNAME` | **Yes** | - | Phone HTTP API username |
| `PHONE_HTTP_PASSWORD` | **Yes** | - | Phone HTTP API password |
| `REDIS_PASSWORD` | No | - | Redis password (optional) |

### Generate Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Automatic Device Sync

On first startup with an empty database:

1. Container starts and initializes database
2. Checks if `ucm_devices` table is empty
3. If CUCM credentials are configured, automatically syncs devices
4. Continues startup regardless of sync success

**Monitor sync:**
```bash
docker-compose logs alertoffice | grep -i sync
```

**Manual sync from UI:**
- Navigate to **Configurations** page
- Click **"Sync from CUCM"** button

**Manual sync via API:**
```bash
curl -X POST http://localhost:5000/api/sync-devices
```

## Health Checks

Both services have health checks configured:

### alertOffice Health Check

**Endpoint:** `http://localhost:5000/`  
**Interval:** 30 seconds  
**Timeout:** 10 seconds  
**Retries:** 3

**Check status:**
```bash
docker inspect alertoffice --format='{{.State.Health.Status}}'
```

### Redis Health Check

**Command:** `redis-cli ping`  
**Interval:** 10 seconds  
**Timeout:** 5 seconds  
**Retries:** 5

**Check status:**
```bash
docker inspect alertoffice-redis --format='{{.State.Health.Status}}'
```

## Common Operations

### Clean Restart

```bash
# Stop, rebuild, and start
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Reset Everything (Caution!)

```bash
# Stop services
docker-compose down -v

# Clear data
sudo rm -rf /opt/alertoffice/data/*
sudo rm -rf /opt/alertoffice/logs/*

# Restart
docker-compose up -d
```

### View Live Logs

```bash
# All services
docker-compose logs -f

# Just alertoffice
docker-compose logs -f alertoffice

# Just redis
docker-compose logs -f redis

# Last 100 lines
docker-compose logs --tail=100
```

## Backup and Restore

### Backup Everything

```bash
#!/bin/bash
BACKUP_DIR="/backups/alertoffice"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup database
sudo cp /opt/alertoffice/data/ucm_devices.db \
        "$BACKUP_DIR/ucm_devices_$DATE.db"

# Backup logs (compressed)
sudo tar czf "$BACKUP_DIR/logs_$DATE.tar.gz" \
             /opt/alertoffice/logs/*.log

# Backup environment
cp .env "$BACKUP_DIR/env_$DATE"

echo "Backup complete: $BACKUP_DIR"
```

### Restore Database

```bash
# Stop services
docker-compose down

# Restore database file
sudo cp /backups/alertoffice/ucm_devices_20260202.db \
        /opt/alertoffice/data/ucm_devices.db

# Start services
docker-compose up -d
```

### Export/Import Docker Images

```bash
# Save image
docker save -o alertoffice.tar alertoffice

# Load image on another system
docker load -i alertoffice.tar
```

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker-compose logs alertoffice
```

**Common issues:**

1. **Port already in use**
   ```bash
   # Check what's using port 5000
   sudo lsof -i :5000
   
   # Change port in docker-compose.yml
   ports:
     - "5001:5000"
   ```

2. **Environment variables missing**
   ```bash
   # Check .env file exists
   ls -la .env
   
   # Validate required variables
   grep -E '^(APP_SECRET_KEY|CUCM_HOST|CUCM_USERNAME|CUCM_PASSWORD)=' .env
   ```

3. **Volume permission errors**
   ```bash
   # Fix ownership
   sudo chown -R $USER:$USER /opt/alertoffice
   sudo chmod -R 755 /opt/alertoffice
   ```

### Database Issues

**Database locked:**
```bash
# Check for stale connections
docker-compose restart alertoffice
```

**Corrupt database:**
```bash
# Restore from backup
docker-compose down
sudo cp /opt/alertoffice/data/ucm_devices.db.backup \
        /opt/alertoffice/data/ucm_devices.db
docker-compose up -d
```

**Empty database after restart:**
```bash
# Check volume mount
docker inspect alertoffice | grep -A 10 Mounts

# Verify file exists on host
ls -lh /opt/alertoffice/data/
```

### Network Issues

**Can't reach CUCM:**
```bash
# Test from container
docker-compose exec alertoffice ping -c 3 $CUCM_HOST

# Check DNS resolution
docker-compose exec alertoffice nslookup $CUCM_HOST

# Test AXL API
docker-compose exec alertoffice python test_axl_sync.py
```

**Can't reach FreeSWITCH:**
```bash
# Test ESL connection
docker-compose exec alertoffice python freeswitch_esl/troubleshoot_esl.py
```

**Redis connection failed:**
```bash
# Check Redis status
docker-compose ps redis

# Test Redis connection
docker-compose exec redis redis-cli ping
```

### Application Errors

**View detailed logs:**
```bash
# From Docker logs
docker-compose logs -f alertoffice

# From application log files
tail -f /opt/alertoffice/logs/alertoffice.log

# Search for errors
grep -i error /opt/alertoffice/logs/alertoffice.log
```

**Access Python shell:**
```bash
docker-compose exec alertoffice python

>>> from sqlite_crud.ucm_devices import get_all_ucm_devices
>>> devices = get_all_ucm_devices()
>>> print(f"Total devices: {len(devices)}")
```

## Performance Tuning

### Resource Limits

Add to `docker-compose.yml`:

```yaml
services:
  alertoffice:
    # ... other config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Redis Persistence

```yaml
redis:
  command: >
    sh -c "redis-server
    --save 900 1
    --save 300 10
    --save 60 10000
    --requirepass $${REDIS_PASSWORD}"
```

## Production Considerations

### Security

1. **Use strong passwords**
   ```bash
   APP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
   REDIS_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

2. **Restrict file permissions**
   ```bash
   chmod 600 .env
   chmod 700 /opt/alertoffice/data
   ```

3. **Use firewall rules**
   ```bash
   # Only allow localhost to access ports
   sudo ufw allow from 127.0.0.1 to any port 5000
   sudo ufw allow from 127.0.0.1 to any port 6379
   ```

4. **Use reverse proxy (nginx)**
   ```nginx
   server {
       listen 80;
       server_name alertoffice.example.com;
       
       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Monitoring

**System resources:**
```bash
docker stats alertoffice alertoffice-redis
```

**Disk usage:**
```bash
du -sh /opt/alertoffice/*
```

**Log rotation:**
```bash
# Application logs auto-rotate (10MB, 30 days)
# Docker logs need manual configuration

# Add to /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

### Automated Backups

Create a cron job:

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup-script.sh
```

## Updating

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Check logs
docker-compose logs -f alertoffice
```

### Update Base Image

```bash
# Update Dockerfile FROM line
FROM python:3.11-slim  # Change version here

# Rebuild
docker-compose build --no-cache
docker-compose up -d
```

## Uninstall

```bash
# Stop and remove containers
docker-compose down -v

# Remove Docker images
docker rmi alertoffice redis:7-alpine

# Remove data (CAUTION!)
sudo rm -rf /opt/alertoffice

# Remove deployment files
rm -f docker-compose.yml Dockerfile .env
```

## Support

- **Documentation:** [README.md](README.md)
- **Device Sync:** [DEVICE_SYNC.md](DEVICE_SYNC.md)
- **Project Structure:** [STRUCTURE.md](STRUCTURE.md)
