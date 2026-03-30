#!/usr/bin/env python3
"""
Raw socket ESL test — no Genesis. Connects, reads auth/request, sends auth, prints response.
Run from project root: python freeswitch_esl/raw_esl_test.py
"""
import asyncio
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from freeswitch_esl.monitor import FS_HOST, FS_PORT, FS_PASSWORD


async def read_esl_message(reader: asyncio.StreamReader) -> tuple[dict, str]:
    """Read one ESL message (headers + optional body). Returns (headers_dict, body)."""
    headers = {}
    while True:
        line = (await reader.readline()).decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            break
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k] = v
    body = ""
    if "Content-Length" in headers:
        n = int(headers["Content-Length"])
        if n > 0:
            body = (await reader.readexactly(n)).decode("utf-8", errors="replace")
    return headers, body


async def main():
    print(f"Connecting to {FS_HOST}:{FS_PORT} ...")
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(FS_HOST, FS_PORT), timeout=5
    )
    print("Connected. Reading first message (auth/request)...")
    h, b = await read_esl_message(reader)
    print("Headers:", h)
    print("Body:", repr(b)[:200])
    ct = h.get("Content-Type", "")
    if "auth/request" not in ct and "rude-rejection" not in ct:
        print("Unexpected first message; sending auth anyway.")
    print("Sending auth ...")
    writer.write(f"auth {FS_PASSWORD}\n\n".encode())
    await writer.drain()
    print("Reading response ...")
    h2, b2 = await read_esl_message(reader)
    print("Response headers:", h2)
    print("Response body:", repr(b2)[:500])
    writer.close()
    await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
