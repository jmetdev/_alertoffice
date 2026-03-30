#!/usr/bin/env python3
"""
Troubleshoot FreeSWITCH ESL connectivity using freeswitch_esl.esl_client (sync ESLClient).
Run from project root: python freeswitch_esl/troubleshoot_esl.py

Steps: 1) config, 2) TCP connect, 3) ESL connect + auth, 4) api conference json_list.
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from freeswitch_esl.monitor import (
    CONFERENCE_JSON_LIST_CMD,
    FS_HOST,
    FS_PORT,
    FS_PASSWORD,
    FS_CONNECT_TIMEOUT,
    FS_RESPONSE_TIMEOUT,
    _parse_conference_list,
    _parse_conference_list_detail,
)
from freeswitch_esl.esl_client import ESLClient


def mask(s: str) -> str:
    if not s:
        return "(empty)"
    if len(s) <= 2:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]


def main():
    print("=== FreeSWITCH ESL troubleshooting (esl_client) ===\n")
    print("1. Config (from env / defaults)")
    print(f"   FREESWITCH_ESL_HOST   = {FS_HOST!r}")
    print(f"   FREESWITCH_ESL_PORT   = {FS_PORT!r}")
    print(f"   FREESWITCH_ESL_PASSWORD = {mask(FS_PASSWORD)!r}")
    print(f"   FREESWITCH_ESL_CONNECT_TIMEOUT = {FS_CONNECT_TIMEOUT}s")
    print(f"   FREESWITCH_ESL_RESPONSE_TIMEOUT = {FS_RESPONSE_TIMEOUT}s")
    print()

    print("2. TCP connect")
    try:
        import socket
        sock = socket.create_connection((FS_HOST, FS_PORT), timeout=FS_CONNECT_TIMEOUT)
        sock.close()
    except (TimeoutError, OSError) as e:
        print(f"   FAIL — Connection to {FS_HOST}:{FS_PORT} failed: {e}")
        sys.exit(1)
    print(f"   OK — {FS_HOST}:{FS_PORT} is reachable.")
    print()

    print("3. ESL connect + auth (ESLClient)")
    print(f"4. api {CONFERENCE_JSON_LIST_CMD} (with debug)")
    try:
        with ESLClient(
            FS_HOST,
            FS_PORT,
            FS_PASSWORD,
            connect_timeout=FS_CONNECT_TIMEOUT,
            response_timeout=FS_RESPONSE_TIMEOUT,
        ) as client:
            print("   OK — Connected and authenticated.")
            print()
            body = client.api(CONFERENCE_JSON_LIST_CMD)
            print("   [DEBUG] First response body length:", len(body))
            print("   [DEBUG] Body preview:", repr(body[:400]) if body else "(empty)")
            print()
        print("   Raw body (full):")
        print("   " + (body[:2000] if body else "(empty)").replace("\n", "\n   "))
        if body and len(body) > 2000:
            print("   ... (truncated)")
        print()
        conferences = _parse_conference_list(body)
        print("   Parsed conference numbers:", conferences if conferences else "(none)")
        detail = _parse_conference_list_detail(body)
        if detail:
            print("   Parsed detail (conference number, SIP URI, name, caller ID):")
            for c in detail:
                print(f"      Conference {c.get('conference', '?')}:")
                for m in c.get("members", []):
                    print(f"         SIP: {m.get('sip_uri', '')}  Name: {m.get('name', '')}  Caller ID: {m.get('caller_id', '')}")
        print()
        print("=== All steps passed. ESL is working. ===")
    except (TimeoutError, OSError) as e:
        print(f"   FAIL — {type(e).__name__}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"   FAIL — {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
