"""Pythonic API over PM2's RPC socket. Mirrors a subset of the `pm2` CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import axon


class NotFound(LookupError):
    """Raised when a target name or id isn't registered with PM2."""


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


def start_ecosystem(
    config: str | Path,
    *,
    only: str | None = None,
    cwd: str | Path | None = None,
) -> "builtins.list[Process]":  # type: ignore[name-defined]
    """Bootstrap one or more apps from an `ecosystem.config.js` file.

    Delegates to the `pm2 start` CLI because evaluating a `.js` config
    requires the node runtime — pure RPC can't do it. The CLI parses the
    file, builds the app config, then sends `prepare` over the same RPC
    socket we use everywhere else.

    Args:
        config: path to ecosystem.config.{js,cjs,json}
        only:   when set, start only the named app — sibling apps in the
                file are untouched, matching `pm2 start --only NAME`
        cwd:    working directory; defaults to where Python is running

    Returns: Process snapshots for whatever was started (filtered to `only`
    when given).
    """
    pm2_bin = shutil.which("pm2")
    if pm2_bin is None:
        raise RuntimeError("pm2 CLI not on PATH — needed to parse .js configs")

    cmd = [pm2_bin, "start", str(config)]
    if only is not None:
        cmd.extend(["--only", only])

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pm2 start failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    all_procs = list()
    if only is not None:
        return [p for p in all_procs if p.name == only]
    return all_procs
