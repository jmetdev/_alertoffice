"""
FreeSWITCH ESL monitor for active conferences.

Uses freeswitch_esl.esl_client (sync ESLClient) to connect, authenticate,
run "api conference json_list", and parse the JSON response.
"""
import json
import os
import re
from typing import Any, List, Tuple

from loguru import logger
from dotenv import load_dotenv

from freeswitch_esl.esl_client import ESLClient

# Load environment variables from .env file
load_dotenv()


# FreeSWITCH ESL connection - all required
FS_HOST = os.getenv("FREESWITCH_ESL_HOST")
FS_PORT = int(os.getenv("FREESWITCH_ESL_PORT", "8021"))
FS_PASSWORD = os.getenv("FREESWITCH_ESL_PASSWORD")
FS_CONNECT_TIMEOUT = float(os.getenv("FREESWITCH_ESL_CONNECT_TIMEOUT", "15"))
FS_RESPONSE_TIMEOUT = float(os.getenv("FREESWITCH_ESL_RESPONSE_TIMEOUT", "15"))

if not FS_HOST:
    raise ValueError("FREESWITCH_ESL_HOST environment variable is required")
if not FS_PASSWORD:
    raise ValueError("FREESWITCH_ESL_PASSWORD environment variable is required")

# ESL API command: conference json_list returns JSON (optional "compact" for shorter output)
CONFERENCE_JSON_LIST_CMD = "conference json_list"

# Match Conference line (text fallback): "+OK Conference 99 (...", "Conference 'name' with N members", etc.
CONF_LINE_RE = re.compile(
    r"Conference\s+(?:'([^']+)'\s+with|(\S+)\s+\()"
)

# Member line (text fallback): member_id;sip_uri;uuid;name;caller_id;flags;...
MEMBER_LINE_RE = re.compile(r"^\d+;[^;]+;[^;]+;[^;]*;[^;]*")


def _normalize_json_body(body: str) -> str:
    """Strip +OK prefix if present so we can parse JSON."""
    if not body:
        return ""
    s = body.strip()
    if s.startswith("+OK "):
        return s[4:].strip()
    return s


def _member_get(m: dict, *keys: str) -> Any:
    """Get value from member dict by key; try exact match then key stripped/lowercased (FreeSWITCH may use '  talking  ' etc)."""
    for k in keys:
        if k in m:
            return m[k]
        k_lower = k.lower().strip()
        for mk, v in m.items():
            if isinstance(mk, str) and mk.strip().lower() == k_lower:
                return v
    return None


def _to_bool(val: Any, default: bool = False) -> bool:
    """Normalize value to bool; accept True, 'true', 1, 'yes', 'on' as True."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    return str(val).strip().lower() in ("true", "1", "yes", "on")


def _parse_json_conference_list(body: str) -> List[dict[str, Any]]:
    """
    Parse FreeSWITCH 'conference json_list' JSON into list of conference detail dicts.
    Conference: conference, participant_count, flags, energy_level, members.
    Member: sip_uri, name, caller_id, has_floor.
    Handles common FreeSWITCH JSON shapes (array of conferences, or object with conferences/rows).
    Returns [] on parse error or empty body.
    """
    raw = _normalize_json_body(body)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # Normalize: may be list of conferences or { "conferences": [...] } or { "rows": [...] }
    if isinstance(data, list):
        conferences = data
    elif isinstance(data, dict):
        conferences = data.get("conferences") or data.get("rows") or data.get("conference") or []
        if isinstance(conferences, dict):
            conferences = [conferences]
    else:
        return []
    result = []
    for conf in conferences:
        if not isinstance(conf, dict):
            continue
        name = (
            conf.get("name")
            or conf.get("conference_name")
            or conf.get("conference")
            or str(conf.get("uuid", ""))
        )
        if not name:
            continue
        # FreeSWITCH may use "members" or "Members"; sometimes members is an object keyed by id
        members_in = (
            conf.get("members")
            or conf.get("Members")
            or conf.get("member")
            or []
        )
        if isinstance(members_in, dict):
            members_in = list(members_in.values())
        if not isinstance(members_in, list):
            members_in = []
        # Conference-level: participant count, flags, energy
        participant_count = conf.get("count")
        if participant_count is None:
            participant_count = conf.get("member_count") or conf.get("participant_count")
        if participant_count is None:
            participant_count = len(members_in)
        if not isinstance(participant_count, int):
            try:
                participant_count = int(participant_count)
            except (TypeError, ValueError):
                participant_count = len(members_in)
        flags_raw = conf.get("flags") or conf.get("conference_flags") or ""
        if isinstance(flags_raw, list):
            flags_list = flags_raw
        else:
            flags_list = [f.strip() for f in str(flags_raw).replace("|", " ").split() if f.strip()]
        energy_level = (
            conf.get("energy_level")
            or conf.get("energy")
            or conf.get("current_energy")
            or conf.get("conference_energy")
            or None
        )
        if energy_level is not None and not isinstance(energy_level, (int, float)):
            try:
                energy_level = int(energy_level)
            except (TypeError, ValueError):
                energy_level = None
        # Log raw conference keys at debug (to match FreeSWITCH json_list structure)
        logger.debug(
            "ESL conference object keys: conf_name={!r} keys={}",
            name,
            list(conf.keys()) if isinstance(conf, dict) else [],
        )
        # Floor holder: conference may have floor_holder / video_floor_holder (member id)
        floor_holder_id = conf.get("floor_holder") or conf.get("video_floor_holder")
        if floor_holder_id is not None and not isinstance(floor_holder_id, (int, str)):
            floor_holder_id = None
        members_out = []
        for m in members_in:
            if not isinstance(m, dict):
                continue
            sip = (
                m.get("channel")
                or m.get("uuid")
                or m.get("sip_uri")
                or ""
            )
            display_name = (
                m.get("caller_id_name")
                or m.get("cid_name")
                or m.get("name")
                or ""
            )
            cid = (
                m.get("caller_id_number")
                or m.get("cid_num")
                or m.get("caller_id")
                or ""
            )
            # Skip empty/placeholder member objects (avoids blank rows in attendees)
            if not sip and not display_name and not cid:
                continue
            # has_floor and talking: FreeSWITCH puts them inside member.flags (object)
            member_id = _member_get(m, "id", "member_id", "uuid") or m.get("id") or m.get("member_id") or m.get("uuid")
            flags_obj = m.get("flags")
            if not isinstance(flags_obj, dict):
                flags_obj = {}

            has_floor = (
                flags_obj.get("has_floor")
                or _member_get(m, "has_floor", "floor", "video_floor")
                or m.get("has_floor")
                or m.get("floor")
                or m.get("video_floor")
            )
            if has_floor is None and floor_holder_id is not None and member_id is not None:
                has_floor = str(member_id) == str(floor_holder_id)
            has_floor = _to_bool(has_floor, default=False)

            talking = (
                flags_obj.get("talking")
                or _member_get(m, "talking", "is_talking", "speaking", "can_speak", "speak")
                or m.get("talking")
                or m.get("is_talking")
                or m.get("speaking")
                or m.get("can_speak")
                or m.get("speak")
            )
            if talking is None:
                flags_str = m.get("member_flags")
                talking = isinstance(flags_str, str) and ("talking" in flags_str.lower() or "speak" in flags_str.lower())
            talking = _to_bool(talking, default=False)
            # Log first member: raw keys and parsed has_floor/talking (to verify API output)
            if not members_out:
                logger.debug(
                    "ESL first member: raw_keys={} parsed has_floor={!r} talking={!r}",
                    list(m.keys()) if isinstance(m, dict) else [],
                    has_floor,
                    talking,
                )
            members_out.append({
                "sip_uri": str(sip),
                "name": str(display_name),
                "caller_id": str(cid),
                "has_floor": has_floor,
                "talking": talking,
            })
        result.append({
            "conference": str(name),
            "participant_count": participant_count,
            "flags": flags_list,
            "energy_level": energy_level,
            "members": members_out,
        })
    return result


def _parse_conference_list(body: str) -> List[str]:
    """Parse conference list (JSON or text fallback) into list of conference names."""
    detail = _parse_json_conference_list(body)
    if detail:
        return [c["conference"] for c in detail]
    # Text fallback for "conference list" or "+OK No active conferences."
    conferences = []
    for line in (body or "").splitlines():
        line = line.strip()
        m = CONF_LINE_RE.search(line)
        if m:
            name = m.group(1) or m.group(2)
            if name:
                conferences.append(name)
    return conferences


def _parse_conference_list_detail(body: str) -> List[dict[str, Any]]:
    """
    Parse FreeSWITCH conference list (JSON from json_list, or text from list) into
    list of conference detail dicts with participant_count, flags, energy_level, members (name, caller_id, has_floor).
    """
    detail = _parse_json_conference_list(body)
    if detail:
        return detail
    # Text fallback: semicolon-separated member lines (no flags/energy/floor)
    result = []
    current_conf = None
    for line in (body or "").splitlines():
        line = line.strip()
        m = CONF_LINE_RE.search(line)
        if m:
            name = m.group(1) or m.group(2)
            if name:
                current_conf = {"conference": name, "participant_count": 0, "flags": [], "energy_level": None, "members": []}
                result.append(current_conf)
            continue
        if current_conf is not None and MEMBER_LINE_RE.match(line):
            parts = line.split(";")
            if len(parts) >= 5:
                current_conf["members"].append({
                    "sip_uri": parts[1].strip(),
                    "name": (parts[3] or "").strip(),
                    "caller_id": (parts[4] or "").strip(),
                    "has_floor": False,
                    "talking": False,
                })
    for c in result:
        c["participant_count"] = len(c["members"])
    return result


def get_active_conferences() -> List[str]:
    """
    Returns a list of active conference names from FreeSWITCH.
    Raises on connection/timeout/auth errors so the caller can show an error.
    """
    with ESLClient(
        FS_HOST,
        FS_PORT,
        FS_PASSWORD,
        connect_timeout=FS_CONNECT_TIMEOUT,
        response_timeout=FS_RESPONSE_TIMEOUT,
    ) as client:
        body = client.api(CONFERENCE_JSON_LIST_CMD)
    logger.debug(
        "ESL conference json_list: body_len={}, body_preview={!r}",
        len(body),
        (body[:500] if body else ""),
    )
    return _parse_conference_list(body)


def get_active_conferences_detail(include_raw: bool = False):
    """
    Returns list of conference detail dicts: conference, participant_count, flags, energy_level,
    members (sip_uri, name, caller_id, has_floor, talking). Raises on connection/timeout/auth errors.
    If include_raw is True, returns (conferences, raw_response_body).
    """
    with ESLClient(
        FS_HOST,
        FS_PORT,
        FS_PASSWORD,
        connect_timeout=FS_CONNECT_TIMEOUT,
        response_timeout=FS_RESPONSE_TIMEOUT,
    ) as client:
        body = client.api(CONFERENCE_JSON_LIST_CMD)
    # Full response in debug so we can see exact FreeSWITCH json_list structure
    logger.debug(
        "ESL conference json_list full response (len={}):\n{}",
        len(body or ""),
        body or "(empty)",
    )
    conferences = _parse_conference_list_detail(body)
    logger.debug(
        "ESL conference json_list parsed: {} conference(s), sample keys per conf: {}",
        len(conferences),
        [list(c.keys()) for c in conferences[:2]],
    )
    if include_raw:
        return conferences, (body or "")
    return conferences


def conference_kick_all(conference_name: str) -> Tuple[bool, str]:
    """
    Run FreeSWITCH command: conference <name> kick all.
    Returns (success, message).
    """
    if not (conference_name or "").strip():
        return False, "Conference name is required"
    name = conference_name.strip()
    cmd = f"conference {name} kick all"
    try:
        with ESLClient(
            FS_HOST,
            FS_PORT,
            FS_PASSWORD,
            connect_timeout=FS_CONNECT_TIMEOUT,
            response_timeout=FS_RESPONSE_TIMEOUT,
        ) as client:
            body = client.api(cmd)
        reply = (body or "").strip()
        if reply.startswith("+OK"):
            return True, reply or "All participants kicked"
        return False, reply or "Unknown response"
    except Exception as e:
        logger.exception("conference_kick_all failed for %s", name)
        return False, str(e).strip() or "ESL error"
