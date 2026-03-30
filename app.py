"""
Simple admin UI for CUCM phone groups using Tabler.io styles.
"""
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file, Response
import asyncio
import json
import os
import socket
import threading
import aiohttp
from loguru import logger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from sqlite_crud.database import initialize_database
from sqlite_crud.groups import create_phone_group, list_phone_groups, get_phone_group, update_phone_group, get_group_by_extension
from sqlite_crud.ucm_devices import search_ucm_devices
from cisco.rislookups import get_device_ip_addresses, get_device_ip_statuses
from cisco.xacml_webhook import parse_xacml_request, build_continue_response
from redis_store.device_ips import store_device_ips_redis, get_device_ips_redis


app = Flask(__name__)

# Create logs directory
logs_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Configure logger to write to logs directory
logger.add(
    os.path.join(logs_dir, "alertoffice.log"),
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level="INFO"
)

# Initialize database
initialize_database()

# App secret key - REQUIRED for session security
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
if not APP_SECRET_KEY:
    raise ValueError("APP_SECRET_KEY environment variable is required")
app.secret_key = APP_SECRET_KEY

# CUCM Connection - all required for device management
CUCM_HOST = os.getenv("CUCM_HOST")
CUCM_USERNAME = os.getenv("CUCM_USERNAME")
CUCM_PASSWORD = os.getenv("CUCM_PASSWORD")
CUCM_VERSION = os.getenv("CUCM_VERSION", "11.5")
CUCM_VERIFY_SSL = os.getenv("CUCM_VERIFY_SSL", "false").lower() in ("true", "1", "yes")

# Phone HTTP credentials - required for phone control
PHONE_HTTP_USERNAME = os.getenv("PHONE_HTTP_USERNAME")
PHONE_HTTP_PASSWORD = os.getenv("PHONE_HTTP_PASSWORD")
PHONE_HTTP_SCHEME = os.getenv("PHONE_HTTP_SCHEME", "http").lower()
PHONE_HTTP_PORT = os.getenv("PHONE_HTTP_PORT", "")

# Redis Connection - required for device IP caching
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None) or None

LOGO_PATH = os.path.join(os.path.dirname(__file__), "alertoffice_logo.png")

def _has_cucm_creds():
    return bool(CUCM_HOST and CUCM_USERNAME and CUCM_PASSWORD)


# Auto-sync devices from CUCM on first load (if database is empty)
def auto_sync_devices_on_startup():
    """Automatically sync devices from CUCM if database is empty"""
    try:
        from sqlite_crud.ucm_devices import get_all_ucm_devices
        from cisco.axl_devices import sync_devices_to_sqlite
        
        # Check if database is empty
        devices = get_all_ucm_devices()
        if len(devices) == 0:
            logger.info("Database is empty. Checking for CUCM credentials...")
            
            # Check if CUCM credentials are configured
            if _has_cucm_creds():
                logger.info(f"CUCM credentials found. Syncing devices from {CUCM_HOST}...")
                try:
                    count = sync_devices_to_sqlite(
                        CUCM_HOST,
                        CUCM_USERNAME,
                        CUCM_PASSWORD,
                        verify_ssl=CUCM_VERIFY_SSL,
                        cucm_version=CUCM_VERSION,
                        search_name='SEP%',
                        debug=False
                    )
                    logger.info(f"✓ Successfully synced {count} devices from CUCM")
                except Exception as sync_error:
                    logger.error(f"Failed to sync devices from CUCM: {sync_error}")
                    logger.warning("Continuing without device sync. You can manually sync later.")
            else:
                logger.warning("CUCM credentials not configured. Skipping automatic device sync.")
                logger.info("Set CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD to enable device sync.")
        else:
            logger.info(f"Database already contains {len(devices)} devices. Skipping auto-sync.")
    except Exception as e:
        logger.error(f"Error during auto-sync check: {e}")
        logger.warning("Continuing startup without device sync.")


# Run auto-sync on startup
auto_sync_devices_on_startup()


def sync_devices_to_redis(device_names):
    if not device_names:
        return
    device_names = sorted(set(device_names))
    if not _has_cucm_creds():
        print("CUCM credentials missing; skipping RIS lookup for Redis cache.")
        return
    device_ips = get_device_ip_addresses(
        CUCM_HOST,
        CUCM_USERNAME,
        CUCM_PASSWORD,
        device_names,
        verify_ssl=CUCM_VERIFY_SSL
    )
    stored = store_device_ips_redis(device_ips, redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)
    missing_ips = [name for name, ip in device_ips.items() if not ip]
    print(f"RIS lookup stored {stored} device IPs in Redis.")
    if missing_ips:
        print(f"RIS lookup returned no IP for {len(missing_ips)} devices.")


def get_or_fetch_device_ips(device_names):
    device_names = sorted(set(device_names))
    device_ips = get_device_ips_redis(device_names, redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)
    missing = [name for name in device_names if not device_ips.get(name)]
    if missing and _has_cucm_creds():
        fetched = get_device_ip_addresses(
            CUCM_HOST,
            CUCM_USERNAME,
            CUCM_PASSWORD,
            missing,
            verify_ssl=CUCM_VERIFY_SSL
        )
        stored = store_device_ips_redis(fetched, redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)
        print(f"RIS lookup stored {stored} missing device IPs in Redis.")
        missing_ips = [name for name, ip in fetched.items() if not ip]
        if missing_ips:
            print(f"RIS lookup returned no IP for {len(missing_ips)} devices.")
        device_ips.update(fetched)
    elif missing and not _has_cucm_creds():
        print("CUCM credentials missing; cannot fetch missing IPs via RIS.")
    return device_ips


def get_device_info_for_group(device_names):
    device_names = sorted(set(device_names))
    device_ips = get_device_ips_redis(device_names, redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)
    status_map = {name: None for name in device_names}

    if _has_cucm_creds():
        ris_info = get_device_ip_statuses(
            CUCM_HOST,
            CUCM_USERNAME,
            CUCM_PASSWORD,
            device_names,
            verify_ssl=CUCM_VERIFY_SSL
        )
        # Store IPs that we got from RIS
        ris_ips = {name: info.get("ip") for name, info in ris_info.items()}
        store_device_ips_redis(ris_ips, redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)

        for name, info in ris_info.items():
            status_map[name] = info.get("status")
            if info.get("ip"):
                device_ips[name] = info.get("ip")
    else:
        print("CUCM credentials missing; cannot fetch device statuses via RIS.")

    return device_ips, status_map


# Ring/alert filename for Play URI (must exist on phone TFTP; common names: Alert1.raw, Beep.raw, etc.)
PHONE_ALERT_RING_FILE = os.getenv("PHONE_ALERT_RING_FILE", "Analog1.raw")
# Seconds to wait after sending Dial before sending Mute/Play/display (avoids dial getting stuck)
PHONE_DIAL_DELAY_SECONDS = float(os.getenv("PHONE_DIAL_DELAY_SECONDS", "2.5"))
# Seconds between Mute and Play requests so the phone processes each separately
PHONE_POST_DIAL_GAP_SECONDS = float(os.getenv("PHONE_POST_DIAL_GAP_SECONDS", "0.5"))


def _build_dial_only_xml(extension: str) -> str:
    """Build CiscoIPPhoneExecute XML with only the Dial command (sent first)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CiscoIPPhoneExecute>'
        f'<ExecuteItem Priority="0" URL="Dial:{extension}"/>'
        '</CiscoIPPhoneExecute>'
    )


def _build_mute_xml() -> str:
    """Build CiscoIPPhoneExecute XML with only Key:Mute (sent as its own request)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CiscoIPPhoneExecute>'
        '<ExecuteItem Priority="0" URL="Key:Mute"/>'
        '</CiscoIPPhoneExecute>'
    )


def _build_play_alert_xml() -> str:
    """Build CiscoIPPhoneExecute XML with only Play (sent as its own request)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CiscoIPPhoneExecute>'
        f'<ExecuteItem Priority="0" URL="Play:{PHONE_ALERT_RING_FILE}"/>'
        '</CiscoIPPhoneExecute>'
    )


def _build_alert_display_xml() -> str:
    """Build CiscoIPPhoneText XML to show 'Alert Office Conference Active' on the phone display."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CiscoIPPhoneText>'
        "<Title>Alert Office</Title>"
        "<Prompt>Conference Active</Prompt>"
        "<Text>Alert Office Conference Active</Text>"
        "</CiscoIPPhoneText>"
    )


async def _post_xml_to_phone(ip_address: str, xml_body: str, command_label: str = "Command") -> bool:
    scheme = PHONE_HTTP_SCHEME or "http"
    port = PHONE_HTTP_PORT.strip()
    host = f"{ip_address}:{port}" if port else ip_address
    url = f"{scheme}://{host}/CGI/Execute"
    timeout = aiohttp.ClientTimeout(total=5)
    auth = None
    if PHONE_HTTP_USERNAME and PHONE_HTTP_PASSWORD:
        auth = aiohttp.BasicAuth(PHONE_HTTP_USERNAME, PHONE_HTTP_PASSWORD)
    ssl_flag = None
    if scheme == "http":
        ssl_flag = False
    logger.info(f"Phone {ip_address}: sending {command_label}")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(
                url,
                data={"XML": xml_body},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=auth,
                ssl=ssl_flag
            ) as response:
                body = await response.text()
                body_preview = (body or "").strip().replace("\n", " ")[:200]
                ok = response.status in (200, 202, 204)
                if ok:
                    logger.info(f"Phone {ip_address}: {command_label} succeeded")
                else:
                    if response.status in (401, 403):
                        logger.error(f"Phone {ip_address}: {command_label} auth failed (status {response.status})")
                    else:
                        logger.error(
                            f"Phone {ip_address}: {command_label} failed (status {response.status}) "
                            f"response='{body_preview}'"
                        )
                return ok
        except Exception:
            logger.exception(f"Phone {ip_address}: {command_label} HTTP error")
            return False


async def _send_dial_to_phones(ip_addresses, extension: str):
    dial_xml = _build_dial_only_xml(extension)
    mute_xml = _build_mute_xml()
    play_xml = _build_play_alert_xml()
    display_xml = _build_alert_display_xml()
    delay_sec = max(0.0, PHONE_DIAL_DELAY_SECONDS)
    gap_sec = max(0.0, PHONE_POST_DIAL_GAP_SECONDS)

    async def send_to_one(ip: str):
        dial_ok = await _post_xml_to_phone(ip, dial_xml, "Dial")
        await asyncio.sleep(delay_sec)
        await _post_xml_to_phone(ip, mute_xml, "Mute")
        await asyncio.sleep(gap_sec)
        await _post_xml_to_phone(ip, play_xml, "Play")
        await _post_xml_to_phone(ip, display_xml, "Text Display")
        return dial_ok

    tasks = [send_to_one(ip) for ip in ip_addresses]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if r is True)
    failures = len(results) - success
    logger.info(f"Dial command sent to {success} phones, {failures} failed.")


def _start_async_dial(ip_addresses, extension: str):
    def runner():
        asyncio.run(_send_dial_to_phones(ip_addresses, extension))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()


@app.get("/")
def index():
    return redirect(url_for("dashboard_page"))


@app.get("/dashboard")
def dashboard_page():
    """Dashboard - Active conference alerts"""
    return render_template("dashboard.html")


@app.get("/groups/create")
def create_group_page():
    """Create new phone group"""
    return render_template("create_groups.html")


@app.get("/groups")
def display_groups_page():
    """Display all phone groups"""
    groups = list_phone_groups()
    return render_template("display_groups.html", groups=groups)


@app.get("/recordings")
def recordings_page():
    """Conference recordings listing page"""
    import os
    import re
    from datetime import datetime
    
    recordings_dir = "/recordings"
    files_data = []
    error = None
    
    try:
        if not os.path.exists(recordings_dir):
            os.makedirs(recordings_dir, exist_ok=True)
            logger.info(f"Created recordings directory: {recordings_dir}")
        
        if os.path.exists(recordings_dir):
            files = [f for f in os.listdir(recordings_dir) if f.endswith(('.wav', '.mp3', '.ogg'))]
            files.sort(reverse=True)  # Newest first
            
            for filename in files:
                filepath = os.path.join(recordings_dir, filename)
                file_stat = os.stat(filepath)
                
                # Parse filename: conference-YYYYMMDD-HHMMSS.ext
                # Example: 19001-20260202-163715.wav
                match = re.match(r'(\d+)-(\d{8})-(\d{6})\.(\w+)$', filename)
                
                if match:
                    conference = match.group(1)
                    date_str = match.group(2)  # YYYYMMDD
                    time_str = match.group(3)  # HHMMSS
                    
                    # Parse date and time
                    try:
                        dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                        date_formatted = dt.strftime("%B %d, %Y")
                        time_formatted = dt.strftime("%I:%M:%S %p")
                        
                        # Calculate relative date
                        now = datetime.now()
                        delta = now - dt
                        if delta.days == 0:
                            date_relative = "Today"
                        elif delta.days == 1:
                            date_relative = "Yesterday"
                        elif delta.days < 7:
                            date_relative = f"{delta.days} days ago"
                        else:
                            date_relative = dt.strftime("%b %d")
                    except ValueError:
                        date_formatted = date_str
                        time_formatted = time_str
                        date_relative = ""
                else:
                    # Fallback for non-standard filenames
                    conference = "Unknown"
                    date_formatted = datetime.fromtimestamp(file_stat.st_mtime).strftime("%B %d, %Y")
                    time_formatted = datetime.fromtimestamp(file_stat.st_mtime).strftime("%I:%M:%S %p")
                    date_relative = ""
                
                # Format file size
                size_bytes = file_stat.st_size
                if size_bytes < 1024:
                    size_formatted = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_formatted = f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    size_formatted = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                
                # Calculate duration (if possible - requires audio library)
                duration = None  # TODO: Could add wave/pydub to get actual duration
                
                files_data.append({
                    "filename": filename,
                    "conference": conference,
                    "date_formatted": date_formatted,
                    "time_formatted": time_formatted,
                    "date_relative": date_relative,
                    "size_formatted": size_formatted,
                    "size_bytes": size_bytes,
                    "duration": duration
                })
    except Exception as e:
        logger.exception("Error listing recordings")
        error = f"Error accessing recordings directory: {str(e)}"
    
    return render_template("recordings.html", files=files_data, error=error)


@app.get("/recordings/download/<path:filename>")
def download_recording(filename):
    """Download a recording file"""
    import os
    from werkzeug.utils import secure_filename
    
    recordings_dir = "/recordings"
    safe_filename = secure_filename(filename)
    filepath = os.path.join(recordings_dir, safe_filename)
    
    if not os.path.exists(filepath):
        flash("Recording not found", "error")
        return redirect(url_for("recordings_page"))
    
    return send_file(filepath, as_attachment=True, download_name=safe_filename)


@app.get("/recordings/stream/<path:filename>")
def stream_recording(filename):
    """Stream a recording file for audio player"""
    import os
    from werkzeug.utils import secure_filename
    
    recordings_dir = "/recordings"
    safe_filename = secure_filename(filename)
    filepath = os.path.join(recordings_dir, safe_filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "Recording not found"}), 404
    
    # Determine mimetype based on extension
    if safe_filename.endswith('.wav'):
        mimetype = 'audio/wav'
    elif safe_filename.endswith('.mp3'):
        mimetype = 'audio/mpeg'
    elif safe_filename.endswith('.ogg'):
        mimetype = 'audio/ogg'
    else:
        mimetype = 'audio/wav'
    
    return send_file(filepath, mimetype=mimetype)


@app.post("/recordings/delete/<path:filename>")
def delete_recording(filename):
    """Delete a recording file"""
    import os
    from werkzeug.utils import secure_filename
    
    recordings_dir = "/recordings"
    safe_filename = secure_filename(filename)
    filepath = os.path.join(recordings_dir, safe_filename)
    
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Recording not found"}), 404
    
    try:
        os.remove(filepath)
        logger.info(f"Deleted recording: {safe_filename}")
        return jsonify({"success": True, "message": f"Recording {safe_filename} deleted successfully"})
    except Exception as e:
        logger.exception(f"Error deleting recording {safe_filename}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/logs")
def logs_page():
    """Application and FreeSWITCH logs listing page"""
    import os
    from datetime import datetime
    
    app_logs = []
    freeswitch_logs = []
    error = None
    
    try:
        # Application logs (logs directory)
        logs_dir = os.path.join(os.getcwd(), 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir, exist_ok=True)
        
        app_log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
        for filename in sorted(app_log_files, reverse=True):
            filepath = os.path.join(logs_dir, filename)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                size_bytes = stat.st_size
                if size_bytes < 1024:
                    size_formatted = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_formatted = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB"
                
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y %I:%M %p")
                
                app_logs.append({
                    "filename": filename,
                    "size_formatted": size_formatted,
                    "size_bytes": size_bytes,
                    "modified": modified
                })
        
        # FreeSWITCH logs (/logs directory)
        freeswitch_dir = "/bridge/logs"
        if os.path.exists(freeswitch_dir):
            fs_files = [f for f in os.listdir(freeswitch_dir) if f.endswith('.log')]
            for filename in sorted(fs_files, reverse=True):
                filepath = os.path.join(freeswitch_dir, filename)
                stat = os.stat(filepath)
                size_bytes = stat.st_size
                if size_bytes < 1024:
                    size_formatted = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_formatted = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB"
                
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y %I:%M %p")
                
                freeswitch_logs.append({
                    "filename": filename,
                    "size_formatted": size_formatted,
                    "size_bytes": size_bytes,
                    "modified": modified
                })
    except Exception as e:
        logger.exception("Error listing log files")
        error = f"Error accessing log files: {str(e)}"
    
    return render_template("logs.html", app_logs=app_logs, freeswitch_logs=freeswitch_logs, error=error)


@app.get("/logs/view")
def view_log():
    """View a specific log file"""
    import os
    from werkzeug.utils import secure_filename
    
    filename = request.args.get("file", "")
    log_type = request.args.get("type", "app")  # 'app' or 'freeswitch'
    tail_lines = int(request.args.get("lines", "500"))
    
    if not filename:
        flash("No log file specified", "error")
        return redirect(url_for("logs_page"))
    
    safe_filename = secure_filename(filename)
    
    # Determine log directory based on type
    if log_type == "freeswitch":
        log_dir = "/bridge/logs"
    else:
        log_dir = os.path.join(os.getcwd(), 'logs')
    
    filepath = os.path.join(log_dir, safe_filename)
    
    if not os.path.exists(filepath):
        flash("Log file not found", "error")
        return redirect(url_for("logs_page"))
    
    try:
        # Get file stats
        stat = os.stat(filepath)
        size_bytes = stat.st_size
        if size_bytes < 1024:
            file_size = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            file_size = f"{size_bytes / 1024:.1f} KB"
        else:
            file_size = f"{size_bytes / (1024 * 1024):.1f} MB"
        
        # Read last N lines
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            total_lines = len(lines)
            content_lines = lines[-tail_lines:] if len(lines) > tail_lines else lines
            content = ''.join(content_lines)
        
        return render_template(
            "log_viewer.html",
            filename=safe_filename,
            log_type=log_type,
            content=content,
            file_size=file_size,
            line_count=total_lines,
            tail_lines=len(content_lines)
        )
    except Exception as e:
        logger.exception(f"Error reading log file {safe_filename}")
        return render_template(
            "log_viewer.html",
            filename=safe_filename,
            log_type=log_type,
            error=f"Error reading log file: {str(e)}",
            content="",
            file_size="0 B",
            line_count=0,
            tail_lines=0
        )


@app.get("/logs/download")
def download_log():
    """Download a log file"""
    import os
    from werkzeug.utils import secure_filename
    
    filename = request.args.get("file", "")
    log_type = request.args.get("type", "app")
    
    if not filename:
        flash("No log file specified", "error")
        return redirect(url_for("logs_page"))
    
    safe_filename = secure_filename(filename)
    
    # Determine log directory based on type
    if log_type == "freeswitch":
        log_dir = "/bridge/logs"
    else:
        log_dir = os.path.join(os.getcwd(), 'logs')
    
    filepath = os.path.join(log_dir, safe_filename)
    
    if not os.path.exists(filepath):
        flash("Log file not found", "error")
        return redirect(url_for("logs_page"))
    
    return send_file(filepath, as_attachment=True, download_name=safe_filename)


@app.get("/configurations")
def configurations_page():
    """System configuration and status page"""
    import redis
    from redis_store.device_ips import get_all_device_keys_redis
    from sqlite_crud.ucm_devices import get_all_ucm_devices
    
    # Gather configuration status
    config = {
        "cucm": {
            "host": CUCM_HOST,
            "username": CUCM_USERNAME,
            "configured": bool(CUCM_HOST and CUCM_USERNAME and CUCM_PASSWORD),
            "verify_ssl": CUCM_VERIFY_SSL
        },
        "freeswitch": {
            "host": None,
            "port": None,
            "connect_timeout": None,
            "response_timeout": None,
            "configured": False
        },
        "redis": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "available": False,
            "keys_count": 0
        },
        "sqlite": {
            "path": "data/ucm_devices.db",
            "groups_count": len(list_phone_groups()),
            "devices_count": 0
        },
        "phone_http": {
            "username": PHONE_HTTP_USERNAME,
            "scheme": PHONE_HTTP_SCHEME,
            "port": PHONE_HTTP_PORT,
            "configured": bool(PHONE_HTTP_USERNAME and PHONE_HTTP_PASSWORD)
        },
        "env": {
            "app_secret_key": bool(APP_SECRET_KEY),
            "cucm_host": CUCM_HOST,
            "cucm_username": CUCM_USERNAME,
            "freeswitch_host": None,
            "phone_http_username": PHONE_HTTP_USERNAME
        }
    }
    
    # Check FreeSWITCH config
    try:
        from freeswitch_esl.monitor import FS_HOST, FS_PORT, FS_PASSWORD, FS_CONNECT_TIMEOUT, FS_RESPONSE_TIMEOUT
        config["freeswitch"]["host"] = FS_HOST
        config["freeswitch"]["port"] = FS_PORT
        config["freeswitch"]["connect_timeout"] = FS_CONNECT_TIMEOUT
        config["freeswitch"]["response_timeout"] = FS_RESPONSE_TIMEOUT
        config["freeswitch"]["configured"] = bool(FS_HOST and FS_PASSWORD)
        config["env"]["freeswitch_host"] = FS_HOST
    except Exception:
        pass
    
    # Check Redis availability
    try:
        keys = get_all_device_keys_redis(redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD)
        config["redis"]["available"] = True
        config["redis"]["keys_count"] = len(keys)
        config["redis"]["error"] = None
    except Exception as e:
        config["redis"]["error"] = str(e)
        logger.error(f"Redis connection test failed: {e}")
    
    # Check SQLite device count
    try:
        devices = get_all_ucm_devices()
        config["sqlite"]["devices_count"] = len(devices)
    except Exception:
        pass
    
    return render_template("configurations.html", config=config)


@app.get("/admin")
def admin_page():
    """Legacy admin page - redirect to dashboard"""
    return redirect(url_for("dashboard_page"))


@app.get("/api/active-alerts")
def api_active_alerts():
    """JSON endpoint for Active Alerts card; does not block page load. Add ?debug=1 to include raw FreeSWITCH response."""
    try:
        from freeswitch_esl.monitor import get_active_conferences_detail
        debug = request.args.get("debug", "").strip().lower() in ("1", "true", "yes")
        if debug:
            conferences, raw_response = get_active_conferences_detail(include_raw=True)
            logger.info(f"Active alerts: fetched {len(conferences)} conference(s) from FreeSWITCH (debug=1)")
            return jsonify({"conferences": conferences, "debug": {"raw_response": raw_response}})
        conferences = get_active_conferences_detail()
        logger.info(f"Active alerts: fetched {len(conferences)} conference(s) from FreeSWITCH")
        return jsonify({"conferences": conferences})
    except (TimeoutError, socket.timeout):
        logger.warning("FreeSWITCH ESL: connection or response timed out.")
        return jsonify({
            "error": "FreeSWITCH ESL timed out. If FreeSWITCH shows no errors, the connection may not be reaching it (firewall/host). Try increasing FREESWITCH_ESL_CONNECT_TIMEOUT and FREESWITCH_ESL_RESPONSE_TIMEOUT."
        })
    except (ConnectionError, OSError) as e:
        logger.warning("FreeSWITCH ESL: connection failed: %s", e)
        return jsonify({
            "error": f"Cannot reach FreeSWITCH ESL ({e}). Check host, port, and firewall."
        })
    except Exception as e:
        logger.exception("Failed to fetch active conferences from FreeSWITCH.")
        msg = str(e).strip() or "Unknown error"
        return jsonify({
            "error": f"Cannot connect to FreeSWITCH ESL: {msg}. Check host/port/password."
        })


@app.post("/api/conferences/<conference_name>/kick-all")
def api_conference_kick_all(conference_name: str):
    """Kick all participants from a conference via FreeSWITCH: conference <name> kick all."""
    try:
        from freeswitch_esl.monitor import conference_kick_all
        success, message = conference_kick_all(conference_name)
        if success:
            logger.info("Conference %s: kick all succeeded: %s", conference_name, message)
            return jsonify({"ok": True, "message": message})
        logger.warning("Conference %s: kick all failed: %s", conference_name, message)
        return jsonify({"ok": False, "error": message}), 400
    except Exception as e:
        logger.exception("Conference kick-all failed for %s", conference_name)
        return jsonify({"ok": False, "error": str(e).strip() or "ESL error"}), 500


@app.get("/")
def root():
    return redirect(url_for("admin_page"))


@app.get("/alertoffice_logo.png")
def alertoffice_logo():
    return send_file(LOGO_PATH)


@app.post("/groups/create")
def create_group():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    extension = request.form.get("extension", "").strip()
    devices_raw = request.form.get("devices", "[]")

    if not name:
        flash("Group name is required.", "error")
        return redirect(url_for("create_group_page"))

    try:
        device_names = json.loads(devices_raw)
        if not isinstance(device_names, list):
            device_names = []
    except json.JSONDecodeError:
        device_names = []

    create_phone_group(
        name=name,
        description=description or None,
        extension=extension or None,
        device_names=device_names
    )

    try:
        sync_devices_to_redis(device_names)
    except ConnectionError as e:
        logger.exception("Redis connection error while syncing group devices.")
        flash("Redis connection error. IP cache not updated.", "error")
    
    flash(f"Group '{name}' created successfully!", "success")
    return redirect(url_for("display_groups_page"))


@app.post("/groups/<int:group_id>/edit")
def update_group(group_id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    extension = request.form.get("extension", "").strip()
    devices_raw = request.form.get("devices", "[]")

    if not name:
        group = get_phone_group(group_id)
        device_ips = get_device_ips_redis(group["devices"], redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD) if group else {}
        return render_template(
            "edit_group.html",
            group=group,
            device_ips=device_ips,
            error="Group name is required."
        )

    try:
        device_names = json.loads(devices_raw)
        if not isinstance(device_names, list):
            device_names = []
    except json.JSONDecodeError:
        device_names = []

    updated = update_phone_group(
        group_id=group_id,
        name=name,
        description=description or None,
        extension=extension or None,
        device_names=device_names
    )

    if updated:
        try:
            sync_devices_to_redis(device_names)
        except ConnectionError as e:
            logger.exception("Redis connection error while syncing updated group devices.")
            flash("Redis connection error. IP cache not updated.", "error")
        
        flash(f"Group '{name}' updated successfully!", "success")

    return redirect(url_for("display_groups_page"))


@app.get("/api/devices")
def api_devices():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify([])
    results = search_ucm_devices(query)
    return jsonify(results)


@app.post("/api/sync-devices")
def api_sync_devices():
    """Synchronize devices from CUCM via AXL API"""
    try:
        from cisco.axl_devices import sync_devices_to_sqlite
        
        if not _has_cucm_creds():
            return jsonify({
                "success": False,
                "error": "CUCM credentials not configured. Set CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD environment variables."
            }), 400
        
        logger.info(f"Manual device sync triggered from {CUCM_HOST}...")
        
        count = sync_devices_to_sqlite(
            CUCM_HOST,
            CUCM_USERNAME,
            CUCM_PASSWORD,
            verify_ssl=CUCM_VERIFY_SSL,
            cucm_version=CUCM_VERSION,
            search_name='SEP%',
            debug=False
        )
        
        logger.info(f"✓ Successfully synced {count} devices")
        
        return jsonify({
            "success": True,
            "count": count,
            "message": f"Successfully synced {count} devices from CUCM"
        })
        
    except Exception as e:
        logger.error(f"Device sync failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.get("/api/groups/<int:group_id>")
def api_group_details(group_id):
    group = get_phone_group(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    try:
        device_ips, status_map = get_device_info_for_group(group["devices"])
    except ConnectionError as e:
        logger.exception(f"Redis connection error while serving group details API. Redis config: host={REDIS_HOST}, port={REDIS_PORT}")
        return jsonify({
            "error": f"Redis connection error. IP cache unavailable. (host={REDIS_HOST}:{REDIS_PORT})",
            "details": str(e)
        }), 500
    return jsonify({
        "group": group,
        "device_ips": device_ips,
        "status_map": status_map
    })


@app.post("/api/groups/<int:group_id>/dial")
def api_group_dial(group_id):
    group = get_phone_group(group_id)
    if not group:
        logger.error(f"Dial request failed: group {group_id} not found.")
        return jsonify({"error": "Group not found"}), 404
    payload = request.get_json(silent=True) or {}
    extension = (payload.get("extension") or group.get("extension") or "8888").strip()
    device_ips, _ = get_device_info_for_group(group["devices"])
    ip_addresses = [ip for ip in device_ips.values() if ip]
    if not ip_addresses:
        logger.error(f"Dial request failed: no IPs for group {group_id}.")
        return jsonify({"error": "No IPs available for this group."}), 400
    _start_async_dial(ip_addresses, extension)
    return jsonify({
        "queued": True,
        "extension": extension,
        "device_count": len(ip_addresses)
    })


@app.route("/webhooks/xacml", methods=["POST", "HEAD"])
def xacml_webhook():
    if request.method == "HEAD":
        return "", 204
    xml_text = request.data.decode("utf-8", errors="ignore")
    try:
        parsed = parse_xacml_request(xml_text)
    except Exception:
        logger.exception("Failed to parse XACML request.")
        response_xml = build_continue_response()
        return Response(response_xml, mimetype="application/xml")

    called_number = parsed.get("called_number")
    calling_number = parsed.get("calling_number")
    transformedcdpn = parsed.get("transformedcdpn")
    logger.info(
        f"XACML received called_number={called_number}, calling_number={calling_number}, "
        f"transformedcdpn={transformedcdpn}"
    )

    lookup_number = transformedcdpn or called_number
    if lookup_number:
        group = get_group_by_extension(lookup_number)
        if group:
            device_ips, _ = get_device_info_for_group(group["devices"])
            ip_addresses = [ip for ip in device_ips.values() if ip]
            if ip_addresses:
                extension = group.get("extension") or lookup_number
                _start_async_dial(ip_addresses, extension)
            else:
                logger.error(f"XACML: no IPs available for group extension {lookup_number}.")
        else:
            logger.error(f"XACML: no group found for extension {lookup_number}.")

    response_xml = build_continue_response()
    return Response(response_xml, mimetype="application/xml")


if __name__ == "__main__":
    app.run(debug=True)
