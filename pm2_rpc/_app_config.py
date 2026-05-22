"""Build the env dict that PM2's `prepare` RPC expects.

This is the Python equivalent of the MVP-relevant 60% of PM2's
`Common.prepareAppConf` (node_modules/pm2/lib/Common.js). It is intentionally
minimal: fork-mode only, extension-based interpreter resolution, defaults for
log/pid paths. No cluster mode, no NVM pinning, no filter_env edge cases.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

from ._types import AppConfig

# PM2 stores all per-process files under ~/.pm2/ — log/pid templates here mirror
# what `Common.sink` does in lib/Common.js so the daemon's executeApp finds
# everything where it expects to.
_PM2_HOME = Path.home() / ".pm2"
_LOG_DIR = _PM2_HOME / "logs"
_PID_DIR = _PM2_HOME / "pids"

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
    """Resolve `script` to an absolute path relative to `cwd`.

    Intentionally does NOT fall back to $PATH (unlike lib/Common.js lines
    148-163) — silently turning `pm2.start("python3")` into a thrashing
    interpreter process is a worse UX than a clean FileNotFoundError. Pass
    `shutil.which(...)`'s result if you actually want a PATH binary.
    """
    p = Path(script)
    candidate = p if p.is_absolute() else cwd / p
    if not candidate.is_file():
        raise FileNotFoundError(f"script not found: {script}")
    return candidate.resolve()


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

    Matches PM2's `~/.pm2/logs/<name>-out.log` / `<name>-error.log` /
    `<name>.log` and `~/.pm2/pids/<name>.pid` conventions.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "pm_out_log_path": str(_LOG_DIR / f"{name}-out.log"),
        "pm_err_log_path": str(_LOG_DIR / f"{name}-error.log"),
        "pm_log_path": str(_LOG_DIR / f"{name}.log"),
        "pm_pid_path": str(_PID_DIR / f"{name}.pid"),
    }


def _merge_env(extra: dict[str, str] | None, *, interpreter: str) -> dict[str, str]:
    """Merge `extra` over `os.environ`; auto-set PYTHONUNBUFFERED for Python.

    The PYTHONUNBUFFERED behavior mirrors lib/Common.js line 474 — without it,
    `print()` output won't reach the PM2 log file until the buffer flushes,
    which can be many seconds for sleepy processes.
    """
    merged: dict[str, str] = dict(os.environ)
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
    merge_logs: bool = False,
) -> AppConfig:
    """Build the env dict to pass to `axon.rpc_call("prepare", env_dict)`.

    Output shape matches what PM2's `God.prepare` reads (see lib/God.js lines
    109-227, lib/God/ForkMode.js lines 36-86).
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

    return {
        "name": safe_name,
        "script": str(script_path),
        "pm_exec_path": str(script_path),
        "pm_cwd": str(cwd_path),
        "exec_interpreter": interp,
        "exec_mode": "fork_mode",
        "env": _merge_env(env, interpreter=interp),
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
