"""
Minimal pm2-axon / pm2-axon-rpc client.

Wire stack:

    AMP framing -> amp-message arg packing -> axon-rpc body

AMP framing (one frame per message):
    1 byte: (version << 4) | argc        # version = 1, argc = 0..15
    for each arg:
        4 bytes big-endian length
        <length> bytes of arg data

amp-message arg encoding:
    string -> b"s:" + utf8(s)
    object -> b"j:" + utf8(json.dumps(obj))
    bytes  -> raw

axon-rpc REQ/REP body (arg 0 is the message; arg 1 is the REQ id echoed back):
    request : {"type": "call", "method": <name>, "args": [...]}
    reply   : {"args": [<result>...]}  or  {"error": "...", "stack": "..."}
"""

from __future__ import annotations

import json
import os
import socket
import struct
from pathlib import Path
from typing import Any

SOCK_PATH = Path.home() / ".pm2" / "rpc.sock"
AMP_VERSION = 1


class PM2Error(RuntimeError):
    """Raised when the daemon returns an error reply."""


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("PM2 daemon closed the socket mid-frame")
        buf.extend(chunk)
    return bytes(buf)


def _pack_arg(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        return b"s:" + value.encode("utf-8")
    return b"j:" + json.dumps(value, separators=(",", ":")).encode("utf-8")


def _unpack_arg(raw: bytes) -> Any:
    if raw[:2] == b"j:":
        return json.loads(raw[2:].decode("utf-8"))
    if raw[:2] == b"s:":
        return raw[2:].decode("utf-8")
    return raw


def _encode_amp(args: list[Any]) -> bytes:
    if not 0 <= len(args) <= 0xF:
        raise ValueError("AMP supports at most 15 args per message")
    packed = [_pack_arg(a) for a in args]
    out = bytearray()
    out.append((AMP_VERSION << 4) | len(packed))
    for p in packed:
        out.extend(struct.pack(">I", len(p)))
        out.extend(p)
    return bytes(out)


def _read_amp(sock: socket.socket) -> list[Any]:
    meta = _recv_exact(sock, 1)[0]
    version = meta >> 4
    argc = meta & 0x0F
    if version != AMP_VERSION:
        raise ValueError(f"unsupported AMP version {version}")
    args = []
    for _ in range(argc):
        (length,) = struct.unpack(">I", _recv_exact(sock, 4))
        args.append(_unpack_arg(_recv_exact(sock, length)))
    return args


def rpc_call(method: str, *args: Any, timeout: float = 10.0) -> Any:
    """Make one axon-rpc call against PM2's daemon and return its result list."""
    req_id = f"{os.getpid()}:0"
    body = {"type": "call", "method": method, "args": list(args)}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(SOCK_PATH))
        s.sendall(_encode_amp([body, req_id]))
        reply_args = _read_amp(s)

    if len(reply_args) < 2:
        raise PM2Error(f"unexpected reply shape: {reply_args!r}")
    msg, echoed_id = reply_args[0], reply_args[1]
    if echoed_id != req_id:
        raise PM2Error(f"id mismatch: sent {req_id!r}, got {echoed_id!r}")
    if isinstance(msg, dict) and "error" in msg:
        raise PM2Error(f"{msg['error']}\n{msg.get('stack', '')}".rstrip())
    if isinstance(msg, dict) and "args" in msg:
        return msg["args"]
    return msg


def list_methods() -> dict:
    """Ask the daemon what methods it exposes (uses the {type:'methods'} body)."""
    req_id = f"{os.getpid()}:0"
    body = {"type": "methods"}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        s.connect(str(SOCK_PATH))
        s.sendall(_encode_amp([body, req_id]))
        reply_args = _read_amp(s)
    return reply_args[0].get("methods", {})
