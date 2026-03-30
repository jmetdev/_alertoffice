"""
Minimal synchronous FreeSWITCH ESL client (no Genesis, no async).

Connects via TCP, authenticates, sends api commands. For "api <cmd>" FreeSWITCH
sends two messages: command/reply then api/response; we read both and return
the api/response body.

Based on the ESL protocol; compatible with FreeSWITCH Event Socket.
"""
import socket
from typing import Tuple


def _header_get(headers: dict, key: str) -> str:
    """Get header value case-insensitively."""
    key_lower = key.lower()
    for k, v in headers.items():
        if k.lower() == key_lower:
            return v or ""
    return ""


class ESLClient:
    """
    Synchronous FreeSWITCH ESL client.
    Connect, authenticate, run api commands, disconnect.
    Uses a read buffer so when FreeSWITCH sends multiple messages in one TCP
    packet (e.g. command/reply + api/response), we parse one message at a time
    and don't lose the second.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        connect_timeout: float = 15.0,
        response_timeout: float = 15.0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.connect_timeout = connect_timeout
        self.response_timeout = response_timeout
        self._sock: socket.socket | None = None
        self._read_buf = b""

    def _read_esl_message(self) -> Tuple[dict, str]:
        """Read one ESL message (headers + body). Uses _read_buf for leftover data."""
        sock = self._sock
        if not sock:
            return {}, ""
        while b"\n\n" not in self._read_buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            self._read_buf += chunk
        if not self._read_buf:
            return {}, ""
        head_part, _, rest = self._read_buf.partition(b"\n\n")
        headers = {}
        for line in head_part.decode("utf-8", errors="replace").splitlines():
            line = line.rstrip("\r")
            if ": " in line:
                k, v = line.split(": ", 1)
                headers[k.strip()] = v.strip()
        body = ""
        content_len = _header_get(headers, "Content-Length")
        if content_len:
            try:
                n = int(content_len.split("\n")[0].strip())
                if n > 0:
                    body_buf = rest[:n] if len(rest) >= n else rest
                    while len(body_buf) < n:
                        body_buf += sock.recv(min(4096, n - len(body_buf)))
                    body = body_buf[:n].decode("utf-8", errors="replace")
                    # Leave any bytes after this message for the next read
                    self._read_buf = rest[n:] if len(rest) > n else b""
                    return headers, body
            except (ValueError, KeyError):
                pass
        # No body or no Content-Length: rest is the start of the next message
        self._read_buf = rest
        return headers, body

    def connect(self) -> None:
        """Connect to FreeSWITCH ESL and authenticate."""
        self._read_buf = b""
        self._sock = socket.create_connection(
            (self.host, self.port),
            timeout=self.connect_timeout,
        )
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.settimeout(self.response_timeout)
        # First message: auth/request
        h1, _ = self._read_esl_message()
        ct = _header_get(h1, "Content-Type")
        if "auth/request" not in ct:
            self.disconnect()
            raise RuntimeError(f"Unexpected first message: {ct}")
        # Send auth
        self._sock.sendall(f"auth {self.password}\n\n".encode())
        h2, _ = self._read_esl_message()
        reply = (_header_get(h2, "Reply-Text") or "").strip()
        if reply != "+OK accepted":
            self.disconnect()
            raise RuntimeError(f"ESL auth failed: {reply or 'no Reply-Text'}")

    def api(self, command: str) -> str:
        """
        Send "api <command>" and return the first response body.
        We only read the first response (command/reply or api/response);
        no second read, so no timeout waiting for a second message.
        """
        if not self._sock:
            raise RuntimeError("ESL not connected")
        self._sock.sendall(f"api {command}\n\n".encode())
        _, body = self._read_esl_message()
        return body or ""

    def disconnect(self) -> None:
        """Close the connection."""
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "ESLClient":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()
