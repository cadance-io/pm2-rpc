"""Public API: function-level wrappers around the daemon's RPC methods.

Returned dicts use PM2's own shape — typically `{"pid": int, "monit": {...},
"pm2_env": {"name": str, "status": str, "pm_id": int, "restart_time": int,
"env": {...}, ...}}`.
"""

from __future__ import annotations

import builtins
import os
import time
from pathlib import Path
from typing import Any

from . import _app_config, axon
from ._types import EcosystemApp, PM2Process


class NotFound(LookupError):
    pass


class UnsupportedConfigError(ValueError):
    pass


def _pm_id(p: PM2Process) -> int:
    return p["pm2_env"]["pm_id"]


def _name(p: PM2Process) -> str:
    return p["pm2_env"]["name"]


def list() -> builtins.list[PM2Process]:
    (raw,) = axon.rpc_call("getMonitorData", {})
    return raw


def exists(name: str) -> bool:
    return any(_name(p) == name for p in list())


def _find(target: str | int, procs: builtins.list[PM2Process]) -> PM2Process | None:
    if isinstance(target, int):
        return next((p for p in procs if _pm_id(p) == target), None)
    return next((p for p in procs if _name(p) == target), None)


def describe(target: str | int) -> PM2Process:
    """Return the process dict for `target` (name or pm_id), or raise NotFound."""
    found = _find(target, list())
    if found is None:
        raise NotFound(f"no PM2 process matches {target!r}")
    return found


def restart(
    target: str | int,
    *,
    env: dict[str, str] | None = None,
    kill_timeout: int | None = None,
) -> PM2Process:
    """Restart a process. `env` is merged via `Object.assign` server-side, so
    only the keys you pass are touched — to bring in your shell env, do
    `restart(name, env={**os.environ, ...})`.

    `kill_timeout` (ms) overrides `pm2_env.kill_timeout` for the next stop +
    every subsequent stop until changed again."""
    pm_id = _pm_id(describe(target))
    opts: dict[str, Any] = {"id": pm_id}
    # PM2's God.restartProcessId does `Common.extend(proc.pm2_env, opts.env)`
    # — it merges every key in `env` onto pm2_env, not just env-var names. We
    # ride that path to update `kill_timeout` live; a top-level opts key is
    # silently ignored by the daemon.
    merged_env: dict[str, Any] = dict(env) if env else {}
    if kill_timeout is not None:
        merged_env["kill_timeout"] = kill_timeout
    if merged_env:
        opts["env"] = merged_env
    axon.rpc_call("restartProcessId", opts)
    return describe(pm_id)


def stop(target: str | int) -> PM2Process:
    """Gracefully stop. Keeps the entry registered (status='stopped')."""
    pm_id = _pm_id(describe(target))
    axon.rpc_call("stopProcessId", pm_id)
    return describe(pm_id)


def delete(target: str | int) -> None:
    axon.rpc_call("deleteProcessId", _pm_id(describe(target)))


def env(target: str | int) -> dict[str, str]:
    return dict(describe(target)["pm2_env"].get("env", {}))


def _read_log(path: str | None, lines: int) -> str:
    """Tail the last `lines` lines of a log file. PM2 keeps the path on disk,
    so we read it directly rather than going through the daemon."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        all_lines = f.read().splitlines()
    return "\n".join(all_lines[-lines:])


def logs(target: str | int, lines: int = 15) -> str:
    """Last `lines` lines of the process's stdout log."""
    return _read_log(describe(target)["pm2_env"].get("pm_out_log_path"), lines)


def error_logs(target: str | int, lines: int = 15) -> str:
    """Last `lines` lines of the process's stderr log."""
    return _read_log(describe(target)["pm2_env"].get("pm_err_log_path"), lines)


def _wait_until_registered(name: str, timeout: float = 5.0) -> PM2Process:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return describe(name)
        except NotFound:
            time.sleep(0.05)
    raise NotFound(f"process {name!r} did not register within {timeout}s")


def start(
    script: str | Path,
    *,
    name: str | None = None,
    interpreter: str | None = None,
    cwd: str | Path | None = None,
    args: builtins.list[str] | str | None = None,
    env: dict[str, str] | None = None,
    autorestart: bool = True,
    out_file: str | Path | None = None,
    error_file: str | Path | None = None,
    merge_logs: bool = False,
    kill_timeout: int | None = None,
    kill_signal: str | None = None,
    watch: bool | builtins.list[str] | None = None,
) -> PM2Process:
    """Launch a new process via the daemon's `prepare` RPC.

    Builds the app config in Python (see `_app_config.build_app_config`) and
    polls until the process appears in `getMonitorData` before returning —
    `prepare` returns before the daemon finishes registering.

    `kill_timeout` (ms) raises PM2's 1600ms graceful-shutdown window; bump it
    for apps whose SIGTERM propagation takes longer (e.g., a uvicorn dev
    server whose multiprocessing-spawn worker needs several seconds).
    `kill_signal` swaps the stop signal (e.g., "SIGINT" for jupyter/ipython
    which trap SIGINT). `watch=True` or a list of paths delegates file-watch
    + restart to PM2 instead of embedding it in the app.
    """
    cfg = _app_config.build_app_config(
        script=script,
        name=name,
        interpreter=interpreter,
        cwd=cwd,
        args=args,
        env=env,
        autorestart=autorestart,
        out_file=out_file,
        error_file=error_file,
        merge_logs=merge_logs,
        kill_timeout=kill_timeout,
        kill_signal=kill_signal,
        watch=watch,
    )
    axon.rpc_call("prepare", cfg)
    return _wait_until_registered(cfg["name"])


_JS_CONFIG_SUFFIXES = (".js", ".cjs", ".mjs")

# Ecosystem fields we accept verbatim from the config file. Names match PM2's
# own vocabulary so users don't have to learn a parallel one.
_ECOSYSTEM_FIELDS = frozenset(
    {
        "name",
        "args",
        "cwd",
        "env",
        "interpreter",
        "out_file",
        "error_file",
        "merge_logs",
        "autorestart",
    }
)


def _load_ecosystem(path: Path) -> builtins.list[EcosystemApp]:
    """Parse an ecosystem config file. .json native, .yaml/.yml via optional
    pyyaml extra. .js/.cjs/.mjs raise (need node to evaluate module.exports)."""
    suffix = path.suffix.lower()
    if suffix in _JS_CONFIG_SUFFIXES:
        raise UnsupportedConfigError(
            f"{path.name}: .js/.cjs/.mjs configs require node to evaluate "
            "`module.exports`. Convert to ecosystem.config.json / .yaml, call "
            "pm2_rpc.start() with each app's fields, or run "
            "`pm2 start <file.js> --only NAME` from the shell."
        )
    if suffix == ".json":
        import json

        data = json.loads(path.read_text())
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as e:
            raise UnsupportedConfigError(
                f"{path.name}: YAML support needs the `yaml` extra — `pip install pm2-rpc[yaml]`."
            ) from e
        data = yaml.safe_load(path.read_text())
    else:
        raise UnsupportedConfigError(f"unrecognized ecosystem extension: {suffix!r}")

    apps = data.get("apps") if isinstance(data, dict) else data
    if apps is None:
        raise UnsupportedConfigError(f"{path.name}: no `apps` field")
    return apps


def _ecosystem_app_to_kwargs(app: EcosystemApp, base_cwd: Path) -> dict[str, Any]:
    """Filter an ecosystem app entry to the kwargs `start()` accepts."""
    # Cast to plain dict for dynamic indexing — TypedDict requires literal
    # string keys, which doesn't compose with our field-set iteration.
    raw: dict[str, Any] = dict(app)
    kwargs: dict[str, Any] = {k: raw[k] for k in _ECOSYSTEM_FIELDS if k in raw}
    # PM2's internal name for `interpreter` is `exec_interpreter`; some older
    # ecosystem files use that. Honor it without inventing a Python alias.
    if "exec_interpreter" in raw and "interpreter" not in kwargs:
        kwargs["interpreter"] = raw["exec_interpreter"]
    kwargs.setdefault("cwd", str(base_cwd))
    return kwargs


def start_ecosystem(
    config: str | Path,
    *,
    only: str | None = None,
    cwd: str | Path | None = None,
) -> builtins.list[PM2Process]:
    """Bootstrap one or more apps from an ecosystem config file.

    `only=NAME` matches `pm2 start --only NAME` — sibling apps in the file are
    untouched. `cwd` defaults to the config file's directory.
    """
    config_path = Path(config).resolve()
    base_cwd = Path(cwd).resolve() if cwd is not None else config_path.parent

    apps = _load_ecosystem(config_path)
    if only is not None:
        apps = [a for a in apps if a.get("name") == only]
        if not apps:
            raise NotFound(f"no app named {only!r} in {config_path.name}")

    started: builtins.list[PM2Process] = []
    for app in apps:
        if "script" not in app:
            raise UnsupportedConfigError(f"app entry missing required `script`: {app!r}")
        started.append(start(app["script"], **_ecosystem_app_to_kwargs(app, base_cwd)))
    return started
