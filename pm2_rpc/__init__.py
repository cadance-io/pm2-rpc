"""Pure-Python client for PM2's daemon RPC socket.

Mirrors a subset of the `pm2` CLI by speaking the daemon's AMP / axon-rpc
wire protocol directly over `~/.pm2/rpc.sock`. No `pm2` binary required at
runtime.
"""

from __future__ import annotations

from ._client import (
    NotFound,
    UnsupportedConfigError,
    delete,
    describe,
    env,
    error_logs,
    exists,
    list,
    logs,
    restart,
    start,
    start_ecosystem,
    stop,
)
from ._types import AppConfig, EcosystemApp, PM2Env, PM2Monit, PM2Process
from .axon import SOCK_PATH, PM2Error, rpc_call

__all__ = [
    # constants + low-level
    "SOCK_PATH",
    "AppConfig",
    "EcosystemApp",
    "NotFound",
    "PM2Env",
    # exceptions
    "PM2Error",
    "PM2Monit",
    # types
    "PM2Process",
    "UnsupportedConfigError",
    "delete",
    "describe",
    "env",
    "error_logs",
    "exists",
    # high-level API
    "list",
    "logs",
    "restart",
    "rpc_call",
    "start",
    "start_ecosystem",
    "stop",
]
