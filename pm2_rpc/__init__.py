"""Pure-Python client for PM2's daemon RPC socket.

Mirrors a subset of the `pm2` CLI by speaking the daemon's AMP / axon-rpc
wire protocol directly over `~/.pm2/rpc.sock`. No `pm2` binary required at
runtime.
"""

from __future__ import annotations

from .axon import PM2Error, SOCK_PATH, rpc_call
from ._client import (
    NotFound,
    UnsupportedConfigError,
    list,
    exists,
    describe,
    start,
    start_ecosystem,
    restart,
    stop,
    delete,
    env,
    logs,
    error_logs,
)

__all__ = [
    "PM2Error",
    "NotFound",
    "UnsupportedConfigError",
    "SOCK_PATH",
    "rpc_call",
    "list",
    "exists",
    "describe",
    "start",
    "start_ecosystem",
    "restart",
    "stop",
    "delete",
    "env",
    "logs",
    "error_logs",
]
