"""Build the env dict that PM2's `prepare` RPC expects.

This is the Python equivalent of the MVP-relevant 60% of PM2's
`Common.prepareAppConf` (node_modules/pm2/lib/Common.js). It is intentionally
minimal: fork-mode only, extension-based interpreter resolution, defaults for
log/pid paths. No cluster mode, no NVM pinning.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path

from ._types import AppConfig, FilterEnv
from .axon import PM2_HOME

# Log/pid templates mirror pm2's paths.js DEFAULT_LOG_PATH / DEFAULT_PID_PATH
# so the daemon's executeApp finds everything where it expects to.
_LOG_DIR = PM2_HOME / "logs"
_PID_DIR = PM2_HOME / "pids"

# Static extension → interpreter table. PM2's lib/interpreter.json is the
# authoritative version; this covers the common cases and skips NVM pinning.
_INTERPRETERS: dict[str, str] = {
    ".py": sys.executable,
    ".js": "node",
    ".mjs": "node",
    ".cjs": "node",
    ".ts": "ts-node",
    ".sh": "bash",
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
}

# PM2 uses the literal string "none" to mean "exec the binary directly, no
# interpreter" (lib/God/ForkMode.js checks for it).
_NO_INTERPRETER = "none"


def _sanitize_name(name: str) -> str:
    """Mirror lib/Common.js line 228 — keep only alphanumerics, `.` and `-`."""
    return re.sub(r"[^a-zA-Z0-9.\-]", "-", name)


def _resolve_script(script: str | Path, cwd: Path) -> Path:
    """Resolve `script` relative to `cwd`, then on $PATH, as lib/Common.js
    lines 131-146 do (`pm2 start npm` runs the `npm` found on $PATH)."""
    p = Path(script)
    candidate = p if p.is_absolute() else cwd / p
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(str(script))
    if found is None:
        raise FileNotFoundError(f"script not found in {cwd} or on $PATH: {script}")
    # abspath, not resolve: a symlink such as a multicall coreutils binary
    # must keep its own name, as pm2's which.js path.resolve keeps it.
    return Path(os.path.abspath(found))


def _resolve_interpreter(ext: str, explicit: str | None) -> str:
    """Pick an interpreter for the given file extension.

    Mirrors lib/Common.js `Common.sink.resolveInterpreter` (lines 442-495)
    for the MVP set. Explicit user value wins; unknown extensions get the
    `"none"` sentinel so PM2 execs the file directly.
    """
    if explicit:
        return explicit
    return _INTERPRETERS.get(ext.lower(), _NO_INTERPRETER)


def _default_paths(name: str) -> dict[str, str]:
    """Compute default log/pid paths for a process named `name`.

    Matches PM2's `$PM2_HOME/logs/<name>-out.log` / `<name>-error.log` /
    `<name>.log` and `$PM2_HOME/pids/<name>.pid` conventions.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "pm_out_log_path": str(_LOG_DIR / f"{name}-out.log"),
        "pm_err_log_path": str(_LOG_DIR / f"{name}-error.log"),
        "pm_log_path": str(_LOG_DIR / f"{name}.log"),
        "pm_pid_path": str(_PID_DIR / f"{name}.pid"),
    }


def _filter_env(shell: dict[str, str], filter_env: FilterEnv) -> dict[str, str]:
    """Port of `filterEnv` in lib/Common.js lines 165-179.

    `True` drops the whole shell env. A `str` drops the one var of that exact
    name. A `list` drops every var whose name contains one of its items.
    """
    if filter_env is True:
        return {}
    if filter_env is False:
        return shell
    if isinstance(filter_env, str):
        return {k: v for k, v in shell.items() if k != filter_env}
    return {k: v for k, v in shell.items() if not any(item in k for item in filter_env)}


def _merge_env(
    extra: dict[str, str] | None,
    *,
    interpreter: str,
    cwd: Path,
    filter_env: FilterEnv = False,
) -> dict[str, str]:
    """Build the app env the way lib/Common.js prepareAppConf does.

    The shell env gets `PWD=cwd` (line 116), then `filter_env` (lines 165-185),
    then PYTHONUNBUFFERED for a Python interpreter, then `extra` on top.

    The PYTHONUNBUFFERED behavior mirrors lib/Common.js line 474 — without it,
    `print()` output won't reach the PM2 log file until the buffer flushes,
    which can be many seconds for sleepy processes.
    """
    merged = _filter_env({**os.environ, "PWD": str(cwd)}, filter_env)
    if "python" in os.path.basename(interpreter).lower():
        merged["PYTHONUNBUFFERED"] = "1"
    if extra:
        merged.update({str(k): str(v) for k, v in extra.items()})
    return merged


def build_app_config(
    script: str | Path,
    *,
    name: str | None = None,
    interpreter: str | None = None,
    cwd: str | Path | None = None,
    args: list[str] | str | None = None,
    env: dict[str, str] | None = None,
    autorestart: bool = True,
    out_file: str | Path | None = None,
    error_file: str | Path | None = None,
    merge_logs: bool = True,
    kill_timeout: int | None = None,
    kill_signal: str | None = None,
    watch: bool | list[str] | None = None,
    ignore_watch: list[str] | str | None = None,
    namespace: str = "default",
    wait_ready: bool = False,
    listen_timeout: int | None = None,
    filter_env: FilterEnv = False,
) -> AppConfig:
    """Build the env dict to pass to `axon.rpc_call("prepare", env_dict)`.

    Output shape matches what PM2's `God.prepare` reads (see lib/God.js lines
    109-227, lib/God/ForkMode.js lines 36-86).

    The pm2 CLI fills these app defaults before it calls `prepare`. The
    daemon reads them, so this function sets them too:

    - `treekill: True` (schema.json line 329). lib/God/Methods.js line 240
      kills the whole process tree only when `treekill === true`; without
      it, a grandchild survives `delete`.
    - `autostart: True` (schema.json line 192). lib/God.js line 180 sets
      the first status from it.
    - `instance_var: "NODE_APP_INSTANCE"` (schema.json line 311). lib/God.js
      line 604 names the instance env var with it.
    - `merge_logs: True` (lib/Common.js lines 865-868, fork mode). When it is
      false, lib/God.js line 208 appends `-<pm_id>` to each log path.
    - `PWD=cwd` in the app env (lib/Common.js line 116).
    - `namespace: "default"` (schema.json line 27). lib/God/ActionMethods.js
      line 796 matches a process by it.
    - `wait_ready: False`. lib/God.js lines 323 and 384 mark the process
      online at once unless it is set.
    """
    cwd_path = Path(cwd).resolve() if cwd is not None else Path.cwd()
    script_path = _resolve_script(script, cwd_path)

    raw_name = name or script_path.stem
    safe_name = _sanitize_name(raw_name)

    ext = script_path.suffix
    interp = _resolve_interpreter(ext, interpreter)

    arg_list: list[str]
    if args is None:
        arg_list = []
    elif isinstance(args, str):
        arg_list = shlex.split(args)
    else:
        arg_list = [str(a) for a in args]

    paths = _default_paths(safe_name)
    if out_file is not None:
        paths["pm_out_log_path"] = str(out_file)
    if error_file is not None:
        paths["pm_err_log_path"] = str(error_file)

    cfg: AppConfig = {
        "name": safe_name,
        "script": str(script_path),
        "pm_exec_path": str(script_path),
        "pm_cwd": str(cwd_path),
        "exec_interpreter": interp,
        "exec_mode": "fork_mode",
        "env": _merge_env(env, interpreter=interp, cwd=cwd_path, filter_env=filter_env),
        "namespace": namespace,
        "treekill": True,
        "autostart": True,
        "instance_var": "NODE_APP_INSTANCE",
        "wait_ready": wait_ready,
        "args": arg_list,
        "node_args": [],
        "autorestart": autorestart,
        "instances": 1,
        "merge_logs": merge_logs,
        "vizion": False,
        "pm_out_log_path": paths["pm_out_log_path"],
        "pm_err_log_path": paths["pm_err_log_path"],
        "pm_log_path": paths["pm_log_path"],
        "pm_pid_path": paths["pm_pid_path"],
    }
    if kill_timeout is not None:
        cfg["kill_timeout"] = kill_timeout
    if kill_signal is not None:
        cfg["kill_signal"] = kill_signal
    if watch is not None:
        cfg["watch"] = watch
    if ignore_watch is not None:
        cfg["ignore_watch"] = ignore_watch
    if listen_timeout is not None:
        cfg["listen_timeout"] = listen_timeout
    return cfg
