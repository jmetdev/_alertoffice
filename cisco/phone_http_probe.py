"""
HTTP probe for Cisco phone web interface (reachability / 200 check).
"""
from typing import Any, Dict, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def probe_phone_http(
    ip_address: str,
    scheme: str = "http",
    port: str = "",
    path: str = "/",
    timeout: float = 3.0,
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_tls: bool = False,
) -> Dict[str, Any]:
    """
    GET the phone's web URL; returns whether status code is 200.

    If username/password are set, HTTP Basic auth is sent (helps some firmware
    return 200 on the main page instead of 401).
    """
    scheme = (scheme or "http").lower().strip()
    port = (port or "").strip()
    host = f"{ip_address}:{port}" if port else ip_address
    url_path = path if path.startswith("/") else f"/{path}"
    url = f"{scheme}://{host}{url_path}"
    auth = None
    if username and password:
        auth = (username, password)
    try:
        r = requests.get(
            url,
            timeout=timeout,
            auth=auth,
            verify=verify_tls,
            allow_redirects=True,
        )
        ok = r.status_code == 200
        return {
            "http_ok": ok,
            "http_status": r.status_code,
            "http_error": None if ok else f"HTTP {r.status_code}",
            "http_url": url,
        }
    except requests.RequestException as e:
        return {
            "http_ok": False,
            "http_status": None,
            "http_error": str(e).strip() or "request failed",
            "http_url": url,
        }
