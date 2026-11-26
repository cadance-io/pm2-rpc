"""Public API: function-level wrappers around the daemon's RPC methods.

Returned dicts use PM2's own shape — typically `{"pid": int, "monit": {...},
"pm2_env": {"name": str, "status": str, "pm_id": int, "restart_time": int,
"env": {...}, ...}}`.
"""

from __future__ import annotations

import builtins
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import _app_config, axon
from ._types import EcosystemApp, FilterEnv, PM2Process


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


# pm2 7.0.4 lib/constants.js: KILL_TIMEOUT is line 103, GRACEFUL_LISTEN_TIMEOUT
# line 83. A daemon started with
# PM2_KILL_TIMEOUT or PM2_GRACEFUL_LISTEN_TIMEOUT uses its own value, which a
# client cannot read; pass `timeout` for such a daemon.
_PM2_KILL_TIMEOUT_MS = 1600
_PM2_LISTEN_TIMEOUT_MS = 3000
# The fixed RPC timeout before 0.3.1. It covers the socket round trip and the
# 250 ms retries of stopProcessId while an app is not online yet.
_REPLY_MARGIN_S = 10.0


def _stop_wait(p: PM2Process) -> float:
    """Seconds the daemon can hold a stop reply for `p`.

    lib/God/Methods.js processIsDead (lines 154-209) waits `kill_timeout` for
    the app to exit, sends SIGKILL, then waits `kill_timeout` again before it
    gives up. stopProcessId (lib/God/ActionMethods.js lines 284-339) replies
    only after that.
    """
    kill_timeout_ms = p["pm2_env"].get("kill_timeout") or _PM2_KILL_TIMEOUT_MS
    return 2 * kill_timeout_ms / 1000 + _REPLY_MARGIN_S


def _restart_wait(p: PM2Process) -> float:
    """Seconds the daemon can hold a restart reply for `p`.

    restartProcessId (lib/God/ActionMethods.js lines 387-425) stops the app,
    then starts it. With `wait_ready`, executeApp (lib/God.js lines 384-391)
    replies after the app sends `ready`, or after `listen_timeout`.
    """
    env = p["pm2_env"]
    if not env.get("wait_ready"):
        return _stop_wait(p)
    listen_timeout_ms = env.get("listen_timeout") or _PM2_LISTEN_TIMEOUT_MS
    return _stop_wait(p) + listen_timeout_ms / 1000


def restart(
    target: str | int,
    *,
    env: dict[str, str] | None = None,
    kill_timeout: int | None = None,
    timeout: float | None = None,
) -> PM2Process:
    """Restart a process. `env` is merged via `Object.assign` server-side, so
    only the keys you pass are touched — to bring in your shell env, do
    `restart(name, env={**os.environ, ...})`.

    `kill_timeout` (ms) overrides `pm2_env.kill_timeout` for the next stop +
    every subsequent stop until changed again.

    `timeout` (s) bounds the wait for the daemon's reply, and TimeoutError
    raises past it. The default covers the daemon's own wait: twice the app's
    current `kill_timeout`, plus `listen_timeout` with `wait_ready`, plus 10s.
    """
    p = describe(target)
    pm_id = _pm_id(p)
    opts: dict[str, Any] = {"id": pm_id}
    # God.restartProcessId does `Utility.extend(proc.pm2_env.env, env)`, and
    # executeApp (lib/God.js line 178) copies every key of pm2_env.env onto
    # pm2_env at the start that follows the stop. We ride that path to update
    # `kill_timeout`; a top-level opts key is silently ignored by the daemon.
    merged_env: dict[str, Any] = dict(env) if env else {}
    if kill_timeout is not None:
        merged_env["kill_timeout"] = kill_timeout
    if merged_env:
        opts["env"] = merged_env
    wait = _restart_wait(p) if timeout is None else timeout
    axon.rpc_call("restartProcessId", opts, timeout=wait)
    return describe(pm_id)


def stop(target: str | int, *, timeout: float | None = None) -> PM2Process:
    """Gracefully stop. Keeps the entry registered (status='stopped').

    `timeout` (s) bounds the wait for the daemon's reply, and TimeoutError
    raises past it. The default covers the daemon's own wait: twice the app's
    `kill_timeout` (pm2 default 1600 ms), plus 10s.
    """
    p = describe(target)
    pm_id = _pm_id(p)
    wait = _stop_wait(p) if timeout is None else timeout
    axon.rpc_call("stopProcessId", pm_id, timeout=wait)
    return describe(pm_id)


def delete(target: str | int, *, timeout: float | None = None) -> None:
    """Stop the process and unregister it. `timeout` works as in `stop`."""
    p = describe(target)
    wait = _stop_wait(p) if timeout is None else timeout
    axon.rpc_call("deleteProcessId", _pm_id(p), timeout=wait)


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
    merge_logs: bool = True,
    kill_timeout: int | None = None,
    kill_signal: str | None = None,
    watch: bool | builtins.list[str] | None = None,
    ignore_watch: builtins.list[str] | str | None = None,
    namespace: str = "default",
    wait_ready: bool = False,
    listen_timeout: int | None = None,
    filter_env: FilterEnv = False,
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
    + restart to PM2 instead of embedding it in the app; `ignore_watch`
    excludes paths from it. `wait_ready=True` keeps the process `launching`
    until it sends `ready` over IPC, or until `listen_timeout` (ms) passes.

    `filter_env` drops shell vars before `env` merges on top: `True` drops
    them all, a str drops one by exact name, a list drops each var whose name
    contains an item.
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
        ignore_watch=ignore_watch,
        namespace=namespace,
        wait_ready=wait_ready,
        listen_timeout=listen_timeout,
        filter_env=filter_env,
    )
    axon.rpc_call("prepare", cfg)
    return _wait_until_registered(cfg["name"])


_JS_CONFIG_SUFFIXES = (".js", ".cjs", ".mjs")

# Ecosystem fields we accept verbatim from the config file. Names match PM2's
# own vocabulary so users don't have to learn a parallel one. Any other key
# raises, so a field this library does not send never vanishes silently.
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
        "kill_timeout",
        "kill_signal",
        "watch",
        "ignore_watch",
        "namespace",
        "wait_ready",
        "listen_timeout",
        "filter_env",
    }
)
_ECOSYSTEM_KEYS = _ECOSYSTEM_FIELDS | {"script", "exec_interpreter"}


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
    """Map an ecosystem app entry to the kwargs `start()` accepts."""
    # Cast to plain dict for dynamic indexing — TypedDict requires literal
    # string keys, which doesn't compose with our field-set iteration.
    raw: dict[str, Any] = dict(app)
    unknown = sorted(raw.keys() - _ECOSYSTEM_KEYS)
    if unknown:
        raise UnsupportedConfigError(
            f"app {raw.get('name', raw.get('script'))!r}: unsupported ecosystem keys {unknown}"
        )
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


def launch_daemon(pm2_root: Path, *, node: str = "node", timeout: float = 10.0) -> None:
    """Start the pm2 God daemon under `PM2_HOME` unless one already answers ping.

    Port of lib/Client.js `launchDaemon` (lines 209-253) and
    `initFileStructure` (lines 130-160). `pm2_root` is the pm2 package dir,
    the one that holds `lib/Daemon.js` and `bin/pm2`. The daemon runs detached
    with its output in `PM2_HOME/pm2.log`. Env `_` names `bin/pm2`, because the
    daemon's crash recovery runs `node $_ update` (lib/Daemon.js line 50).

    Raises FileNotFoundError when `node` or `lib/Daemon.js` is missing,
    PM2Error when the daemon exits before it answers ping, and TimeoutError
    when it does not answer ping in `timeout` seconds.
    """
    if _answers_ping():
        return
    daemon_js = pm2_root / "lib" / "Daemon.js"
    if not daemon_js.is_file():
        raise FileNotFoundError(f"pm2 daemon entrypoint not found: {daemon_js}")
    node_bin = shutil.which(node)
    if node_bin is None:
        raise FileNotFoundError(f"node binary not found on $PATH: {node}")

    home = axon.PM2_HOME
    for sub in ("logs", "pids", "modules"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    module_conf = home / "module_conf.json"
    if not module_conf.exists():
        module_conf.write_text("{}")

    log_path = home / "pm2.log"
    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            [node_bin, str(daemon_js)],
            env={
                "SILENT": "true",
                **os.environ,
                "PM2_HOME": str(home),
                "_": str(pm2_root / "bin" / "pm2"),
            },
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _answers_ping():
            return
        if proc.poll() is not None:
            raise axon.PM2Error(
                f"pm2 daemon exited with code {proc.returncode} before it answered ping; "
                f"see {log_path}"
            )
        time.sleep(0.1)
    raise TimeoutError(f"pm2 daemon did not answer ping within {timeout}s; see {log_path}")


def _answers_ping() -> bool:
    """False only when nothing listens on the socket, as Client.pingDaemon
    decides. A slow reply is a live daemon, so a timeout propagates."""
    try:
        axon.rpc_call("ping")
    except (FileNotFoundError, ConnectionRefusedError):
        return False
    return True
