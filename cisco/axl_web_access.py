"""
CUCM AXL: read phone Web Access from Informix DB (device.tkwebaccess) via executeSQLQuery.
"""
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings
from zeep.helpers import serialize_object
from zeep.transports import Transport
import urllib3

from cisco.axl_devices import DEFAULT_CUCM_VERSION, SCHEMA_DIR

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# CUCM enum TypeWebAccess (typical values; raw integer still returned).
_TK_WEB_ACCESS_LABELS = {
    0: "Disabled",
    1: "Full",
    2: "Read only",
}


def _escape_sql_string(value: str) -> str:
    return (value or "").replace("'", "''")


def _create_axl_client(
    cucm_host: str,
    username: str,
    password: str,
    verify_ssl: bool,
    cucm_version: str,
) -> Client:
    wsdl_path = SCHEMA_DIR / cucm_version / "AXLAPI.wsdl"
    wsdl_location_remote = f"https://{cucm_host}:8443/axl/services/AXLAPIService?wsdl"
    wsdl_location = str(wsdl_path.absolute()) if wsdl_path.exists() else wsdl_location_remote

    session = Session()
    session.verify = verify_ssl
    session.auth = HTTPBasicAuth(username, password)
    transport = Transport(session=session, operation_timeout=15)
    settings = Settings(strict=False)

    client = Client(wsdl_location, transport=transport, settings=settings)
    endpoint_url = f"https://{cucm_host}:8443/axl/services/AXLAPIService"
    if client.service and hasattr(client.service, "_binding_options"):
        client.service._binding_options["address"] = endpoint_url
    return client


def fetch_devices_web_access_tk(
    cucm_host: str,
    username: str,
    password: str,
    device_names: List[str],
    verify_ssl: bool = False,
    cucm_version: Optional[str] = None,
) -> Dict[str, Dict[str, Optional[object]]]:
    """
    For each device name, run executeSQLQuery for tkwebaccess on the device table.

    Returns map: device_name -> {
        tkwebaccess: int | None,
        web_access_label: str | None,
        axl_error: str | None,
    }
    """
    version = cucm_version or DEFAULT_CUCM_VERSION
    out: Dict[str, Dict[str, Optional[object]]] = {}
    for name in device_names:
        out[name] = {
            "tkwebaccess": None,
            "web_access_label": None,
            "axl_error": None,
        }

    if not device_names:
        return out

    try:
        client = _create_axl_client(cucm_host, username, password, verify_ssl, version)
    except Exception as e:
        msg = str(e).strip() or "AXL client error"
        logger.warning("AXL web-access: failed to create client: %s", msg)
        for name in device_names:
            out[name]["axl_error"] = msg
        return out

    for name in device_names:
        safe = _escape_sql_string(name)
        sql = f"select name, tkwebaccess from device where name = '{safe}'"
        try:
            response = client.service.executeSQLQuery(sql=sql)
            data = serialize_object(response) if response else {}
            rows = []
            if data and data.get("return"):
                ret = data["return"]
                row_el = ret.get("row")
                if row_el is None:
                    rows = []
                elif isinstance(row_el, list):
                    rows = row_el
                else:
                    rows = [row_el]

            if not rows:
                out[name]["axl_error"] = "no_row"
                continue

            row = rows[0]
            tk = None
            if isinstance(row, dict):
                # zeep may return {'tkwebaccess': '1', ...} or nested
                raw = row.get("tkwebaccess")
                if raw is not None and raw != "":
                    try:
                        tk = int(str(raw).strip())
                    except ValueError:
                        tk = None
            else:
                tk = getattr(row, "tkwebaccess", None)
                if tk is not None:
                    try:
                        tk = int(str(tk).strip())
                    except ValueError:
                        tk = None

            out[name]["tkwebaccess"] = tk
            if tk is not None:
                label = _TK_WEB_ACCESS_LABELS.get(tk, f"value {tk}")
                out[name]["web_access_label"] = label
        except Exception as e:
            err = str(e).strip() or "executeSQLQuery failed"
            logger.debug("AXL web-access for %s: %s", name, err)
            out[name]["axl_error"] = err

    return out
