"""Pythonic API over PM2's RPC socket. Mirrors a subset of the `pm2` CLI."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import _app_config
import axon


class NotFound(LookupError):
    """Raised when a target name or id isn't registered with PM2."""


class UnsupportedConfigError(ValueError):
    """Raised when an ecosystem config format requires node to evaluate."""


class Process:
    """Thin view over one PM2 process snapshot. Wraps the dict shape returned
    by the daemon's `getMonitorData` so callers can use attribute access."""

    __slots__ = ("_raw",)

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    @property
    def raw(self) -> dict:
        return self._raw

    @property
    def pm2_env(self) -> dict:
        return self._raw.get("pm2_env", {})

    @property
    def pm_id(self) -> int:
        return self.pm2_env.get("pm_id", self._raw.get("pm_id"))

    @property
    def name(self) -> str:
        return self.pm2_env.get("name") or self._raw.get("name", "")

    @property
    def pid(self) -> int | None:
        v = self._raw.get("pid")
        return v if v else None

    @property
    def status(self) -> str:
        return self.pm2_env.get("status", "")

    @property
    def restart_time(self) -> int:
        return self.pm2_env.get("restart_time", 0)

    def __repr__(self) -> str:
        return f"<Process pm_id={self.pm_id} name={self.name!r} status={self.status!r}>"


def list() -> "builtins.list[Process]":  # type: ignore[name-defined]
    """Return every process currently managed by the PM2 daemon."""
    (raw,) = axon.rpc_call("getMonitorData", {})
    return [Process(p) for p in raw]


def exists(name: str) -> bool:
    """True iff a process with that name is registered (any status)."""
    return any(p.name == name for p in list())


def _find(target: str | int, procs: "builtins.list[Process]") -> Process | None:  # type: ignore[name-defined]
    if isinstance(target, int):
        return next((p for p in procs if p.pm_id == target), None)
    return next((p for p in procs if p.name == target), None)


def describe(target: str | int) -> Process:
    """Return the Process for `target` (name or pm_id).

    Mirrors `pm2 describe <name>` — raises NotFound if unregistered, so
    callers can use a try/except as an existence probe.
    """
    found = _find(target, list())
    if found is None:
        raise NotFound(f"no PM2 process matches {target!r}")
    return found


def restart(
    target: str | int,
    *,
    env: dict[str, str] | None = None,
    update_env: bool = False,
) -> Process:
    """Restart a process. Mirrors `pm2 restart <name>` with optional env-merge.

    Args:
        target: process name or pm_id
        env: extra env vars to merge into the process's pm2_env.env
        update_env: when True, current `os.environ` is merged too — mirrors
            `pm2 restart NAME --update-env`. If both are given, `env` takes
            precedence (it's merged last).

    The daemon's restartProcessId accepts `{id, env}` and `Object.assign`s
    env into the existing process env, so this is one round-trip.
    """
    proc = describe(target)
    merged: dict[str, str] = {}
    if update_env:
        merged.update(os.environ)
    if env:
        merged.update(env)
    opts: dict[str, Any] = {"id": proc.pm_id}
    if merged:
        opts["env"] = merged
    axon.rpc_call("restartProcessId", opts)
    return describe(proc.pm_id)


def stop(target: str | int) -> Process:
    """Gracefully stop a process. Keeps the entry registered with PM2
    (status='stopped'), mirroring `pm2 stop <name>`."""
    proc = describe(target)
    axon.rpc_call("stopProcessId", proc.pm_id)
    return describe(proc.pm_id)


def delete(target: str | int) -> None:
    """Remove a process entry entirely, like `pm2 delete <name>`."""
    proc = describe(target)
    axon.rpc_call("deleteProcessId", proc.pm_id)


def env(target: str | int) -> dict[str, str]:
    """The merged env dict the running process actually sees.

    Mirrors `pm2 env <id>` (which prints the same thing line-by-line). Use
    this to short-circuit work like 'already in suite mode, skip restart'.
    """
    return dict(describe(target).pm2_env.get("env", {}))


def logs(target: str | int, lines: int = 15, *, stream: str = "out") -> str:
    """Return the last `lines` lines of the process log.

    Mirrors `pm2 logs <name> --lines N --nostream`. PM2 keeps the log file
    path on disk in pm2_env.pm_out_log_path / pm_err_log_path — we read it
    directly rather than going through the daemon.

    Args:
        target: name or pm_id
        lines:  how many trailing lines to return
        stream: 'out' (stdout) or 'err' (stderr)
    """
    if stream not in ("out", "err"):
        raise ValueError(f"stream must be 'out' or 'err', got {stream!r}")
    proc = describe(target)
    path = proc.pm2_env.get(f"pm_{stream}_log_path")
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        all_lines = f.read().splitlines()
    return "\n".join(all_lines[-lines:])


def _wait_until_registered(name: str, timeout: float = 5.0) -> Process:
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
    args: list[str] | str | None = None,
    env: dict[str, str] | None = None,
    autorestart: bool = True,
    out_file: str | Path | None = None,
    err_file: str | Path | None = None,
    merge_logs: bool = False,
) -> Process:
    """Launch a new process via pure-socket RPC.

    Mirrors `pm2 start <script>` for the fork-mode case. Builds the app
    config in Python (see `_app_config.build_app_config`), sends it to the
    daemon's `prepare` RPC, and waits for the process to appear in
    `getMonitorData` before returning.
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
        err_file=err_file,
        merge_logs=merge_logs,
    )
    axon.rpc_call("prepare", cfg)
    return _wait_until_registered(cfg["name"])


_JS_CONFIG_SUFFIXES = (".js", ".cjs", ".mjs")

# Map ecosystem-file field names (what users write in the JSON/YAML) to the
# kwargs pm2.start() accepts. Anything not in this map is dropped.
_ECOSYSTEM_FIELD_ALIASES: dict[str, str] = {
    "name": "name",
    "script": "script",
    "args": "args",
    "cwd": "cwd",
    "env": "env",
    "interpreter": "interpreter",
    "exec_interpreter": "interpreter",
    "out_file": "out_file",
    "error_file": "err_file",
    "err_file": "err_file",
    "merge_logs": "merge_logs",
    "autorestart": "autorestart",
}


def _load_ecosystem(path: Path) -> "list[dict[str, Any]]":
    """Parse an ecosystem config file. Returns the `apps` list.

    JSON and YAML are loaded natively. `.js` / `.cjs` / `.mjs` raise
    UnsupportedConfigError — evaluating `module.exports` requires node.
    """
    suffix = path.suffix.lower()
    if suffix in _JS_CONFIG_SUFFIXES:
        raise UnsupportedConfigError(
            f"{path.name}: .js/.cjs/.mjs configs require node to evaluate "
            "`module.exports`. Convert to ecosystem.config.json / .yaml, call "
            "pm2.start() with each app's fields, or run "
            "`pm2 start <file.js> --only NAME` from the shell."
        )
    if suffix == ".json":
        import json

        data = json.loads(path.read_text())
    elif suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(path.read_text())
    else:
        raise UnsupportedConfigError(f"unrecognized ecosystem extension: {suffix!r}")

    apps = data.get("apps") if isinstance(data, dict) else data
    if apps is None:
        raise UnsupportedConfigError(f"{path.name}: no `apps` field")
    return apps


def start_ecosystem(
    config: str | Path,
    *,
    only: str | None = None,
    cwd: str | Path | None = None,
) -> "list[Process]":
    """Bootstrap one or more apps from an ecosystem config file (pure socket).

    Supports `.json`, `.yaml`, `.yml`. `.js` / `.cjs` / `.mjs` raise
    UnsupportedConfigError — see the message for workarounds.

    Args:
        config: path to ecosystem.config.{json,yaml,yml}
        only:   when set, start only the named app — sibling apps in the
                file are untouched, matching `pm2 start --only NAME`
        cwd:    working directory for resolving script paths; defaults to
                the config file's directory
    """
    config_path = Path(config).resolve()
    base_cwd = Path(cwd).resolve() if cwd is not None else config_path.parent

    apps = _load_ecosystem(config_path)
    if only is not None:
        apps = [a for a in apps if a.get("name") == only]
        if not apps:
            raise NotFound(f"no app named {only!r} in {config_path.name}")

    started: "list[Process]" = []
    for app in apps:
        if "script" not in app:
            raise UnsupportedConfigError(f"app entry missing required `script`: {app!r}")
        kwargs: dict[str, Any] = {}
        for src_key, dst_key in _ECOSYSTEM_FIELD_ALIASES.items():
            if src_key == "script":
                continue
            if src_key in app:
                kwargs[dst_key] = app[src_key]
        kwargs.setdefault("cwd", str(base_cwd))
        started.append(start(app["script"], **kwargs))
    return started
