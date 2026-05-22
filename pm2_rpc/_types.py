"""TypedDict definitions for the dict shapes pm2_rpc exposes.

These mirror PM2's actual wire shape (node_modules/pm2/lib/God.js plus
lib/Common.js's prepareAppConf output). All inner fields are NotRequired
— PM2 sends a subset depending on process state, and we don't want to
lie about what's present. Extras PM2 may add still flow through at
runtime (TypedDict doesn't reject unknown keys).
"""

# NB: do NOT add `from __future__ import annotations` here — PEP 563 deferred
# evaluation prevents TypedDict.__optional_keys__/__required_keys__ from
# populating correctly on Python 3.11 (see CPython #97727).
from typing import Any, NotRequired, TypedDict


class PM2Monit(TypedDict, total=False):
    cpu: int
    memory: int


class PM2Env(TypedDict, total=False):
    # identity
    name: str
    pm_id: int
    namespace: str
    unique_id: str
    # lifecycle
    status: str  # "online" | "stopped" | "stopping" | "launching" | "errored"
    restart_time: int
    unstable_restarts: int
    created_at: int
    pm_uptime: int
    exit_code: int
    # exec
    pm_exec_path: str
    pm_cwd: str
    exec_interpreter: str
    exec_mode: str  # "fork_mode" | "cluster_mode"
    args: list[str]
    node_args: list[str]
    instances: int
    # logging
    pm_out_log_path: str
    pm_err_log_path: str
    pm_log_path: str
    pm_pid_path: str
    merge_logs: bool
    # env / behavior
    env: dict[str, str]
    autorestart: bool
    autostart: bool
    watch: bool | list[str]
    vizion: bool
    vizion_running: bool
    # PM2 internals — present after `executeApp` runs
    axm_actions: list[Any]
    axm_monitor: dict[str, Any]
    axm_options: dict[str, Any]
    axm_dynamic: dict[str, Any]
    version: str
    kill_timeout: int
    kill_signal: str


class PM2Process(TypedDict):
    pid: NotRequired[int | None]
    pm2_env: PM2Env
    monit: NotRequired[PM2Monit]
    name: NotRequired[str]  # mirror of pm2_env.name at top level


class AppConfig(TypedDict):
    """The env dict pm2_rpc sends to the daemon's `prepare` RPC.

    All keys without `NotRequired` are always emitted by build_app_config()
    and required by the daemon's executeApp. The optional keys (kill_timeout,
    kill_signal, watch) are emitted only when the caller passes them.
    """

    name: str
    script: str
    pm_exec_path: str
    pm_cwd: str
    exec_interpreter: str
    exec_mode: str
    env: dict[str, str]
    args: list[str]
    node_args: list[str]
    autorestart: bool
    instances: int
    merge_logs: bool
    vizion: bool
    pm_out_log_path: str
    pm_err_log_path: str
    pm_log_path: str
    pm_pid_path: str
    kill_timeout: NotRequired[int]
    kill_signal: NotRequired[str]
    watch: NotRequired[bool | list[str]]


class EcosystemApp(TypedDict, total=False):
    """One entry in `apps:` of an ecosystem.config.{json,yaml}.

    Only `script` is truly required by PM2's schema; everything else has
    a sensible default.
    """

    script: str
    name: str
    args: list[str] | str
    cwd: str
    env: dict[str, str]
    interpreter: str
    exec_interpreter: str  # legacy synonym for `interpreter`
    out_file: str
    error_file: str
    merge_logs: bool
    autorestart: bool
