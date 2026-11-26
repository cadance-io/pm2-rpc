"""Pure-Python client for PM2's daemon RPC socket.

Mirrors a subset of the `pm2` CLI by speaking the daemon's AMP / axon-rpc
wire protocol directly over `$PM2_HOME/rpc.sock` (default `~/.pm2`). No `pm2` binary required at
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
    launch_daemon,
    list,
    logs,
    restart,
    start,
    start_ecosystem,
    stop,
)
from ._types import AppConfig, EcosystemApp, FilterEnv, PM2Env, PM2Monit, PM2Process
from .axon import PM2_HOME, SOCK_PATH, PM2Error, rpc_call

__all__ = [
    # constants + low-level
    "PM2_HOME",
    "SOCK_PATH",
    "AppConfig",
    "EcosystemApp",
    "FilterEnv",
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
    "launch_daemon",
    # high-level API
    "list",
    "logs",
    "restart",
    "rpc_call",
    "start",
    "start_ecosystem",
    "stop",
]
