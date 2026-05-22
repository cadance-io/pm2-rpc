"""Pure-Python client for PM2's daemon RPC socket.

Mirrors a subset of the `pm2` CLI by speaking the daemon's AMP / axon-rpc
wire protocol directly over `~/.pm2/rpc.sock`. No `pm2` binary required at
runtime.
"""

from __future__ import annotations

from ._types import AppConfig, EcosystemApp, PM2Env, PM2Monit, PM2Process
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
    # exceptions
    "PM2Error",
    "NotFound",
    "UnsupportedConfigError",
    # types
    "PM2Process",
    "PM2Env",
    "PM2Monit",
    "AppConfig",
    "EcosystemApp",
    # constants + low-level
    "SOCK_PATH",
    "rpc_call",
    # high-level API
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
