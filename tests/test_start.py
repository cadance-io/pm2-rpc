"""pm2_rpc.start(script, name=, ...) launches via the prepare RPC."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

import pm2_rpc as pm2
from tests.conftest import SLEEPER, SPAWNER, unique_name
from tests.conftest import fixture_name as fixture_name


def test_start_returns_online_dict(fixture_name: str) -> None:
    proc = pm2.start(str(SLEEPER), name=fixture_name)
    assert isinstance(proc, dict)
    assert proc["pm2_env"]["name"] == fixture_name
    assert proc["pm2_env"]["status"] == "online"
    assert proc["pid"] > 0


def test_start_registers_in_list(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name)
    assert pm2.exists(fixture_name)


def test_start_passes_env_to_process(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name, env={"APP_MODE": "suite", "FOO": "bar"})
    env = pm2.env(fixture_name)
    assert env["APP_MODE"] == "suite"
    assert env["FOO"] == "bar"


def test_start_writes_to_log(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if "sleeper started" in pm2.logs(fixture_name, lines=5):
            return
        time.sleep(0.1)
    pytest.fail("expected startup line in logs within 3s")


def test_start_name_defaults_to_script_stem(tmp_path: Path) -> None:
    name = unique_name()
    script = tmp_path / f"{name}.py"
    script.write_text(SLEEPER.read_text())
    try:
        proc = pm2.start(str(script))
        assert proc["pm2_env"]["name"] == name
    finally:
        try:
            pm2.delete(name)
        except pm2.NotFound:
            pass


def test_start_missing_script_raises(fixture_name: str) -> None:
    with pytest.raises(FileNotFoundError):
        pm2.start("/no/such/file.py", name=fixture_name)


def test_start_resolves_bare_script_on_path(fixture_name: str, tmp_path: Path) -> None:
    proc = pm2.start("sleep", name=fixture_name, cwd=tmp_path, args="300", interpreter="none")
    assert proc["pm2_env"]["pm_exec_path"] == shutil.which("sleep")


def test_start_passes_kill_timeout_to_pm2_env(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name, kill_timeout=7777)
    assert pm2.describe(fixture_name)["pm2_env"]["kill_timeout"] == 7777


def test_start_passes_kill_signal_to_pm2_env(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name, kill_signal="SIGINT")
    assert pm2.describe(fixture_name)["pm2_env"]["kill_signal"] == "SIGINT"


def test_start_passes_watch_bool_to_pm2_env(fixture_name: str) -> None:
    pm2.start(str(SLEEPER), name=fixture_name, watch=True)
    assert pm2.describe(fixture_name)["pm2_env"]["watch"] is True


def test_start_omits_lifecycle_keys_by_default(fixture_name: str) -> None:
    """No behavior change for existing callers: PM2's own defaults apply."""
    pm2.start(str(SLEEPER), name=fixture_name)
    env = pm2.describe(fixture_name)["pm2_env"]
    assert env.get("kill_timeout") in (None, 1600)
    assert env.get("watch") in (None, False)


def test_start_passes_daemon_fields_to_pm2_env(fixture_name: str) -> None:
    pm2.start(
        str(SLEEPER),
        name=fixture_name,
        namespace="pm2rpc-ns",
        watch=["src"],
        ignore_watch=["node_modules"],
        wait_ready=True,
        listen_timeout=500,
    )
    env = pm2.describe(fixture_name)["pm2_env"]
    assert env["namespace"] == "pm2rpc-ns"
    assert env["ignore_watch"] == ["node_modules"]
    assert env["wait_ready"] is True
    assert env["listen_timeout"] == 500


def test_start_sets_pwd_to_cwd(fixture_name: str, tmp_path: Path) -> None:
    pm2.start(str(SLEEPER), name=fixture_name, cwd=tmp_path)
    assert pm2.env(fixture_name)["PWD"] == str(tmp_path)


def test_start_filter_env_drops_shell_vars_under_app_env(
    fixture_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PM2RPC_DATABASE_URL", "shell")
    monkeypatch.setenv("PM2RPC_KEEP", "shell")
    pm2.start(
        str(SLEEPER),
        name=fixture_name,
        env={"PM2RPC_APP_DATABASE": "app"},
        filter_env=["DATABASE"],
    )
    env = pm2.env(fixture_name)
    assert "PM2RPC_DATABASE_URL" not in env
    assert env["PM2RPC_KEEP"] == "shell"
    assert env["PM2RPC_APP_DATABASE"] == "app"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_delete_kills_grandchild_because_treekill_is_set(fixture_name: str, tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    pm2.start(str(SPAWNER), name=fixture_name, env={"CHILD_PID_FILE": str(pid_file)})
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    child = int(pid_file.read_text())
    assert _alive(child)

    pm2.delete(fixture_name)

    deadline = time.monotonic() + 5
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child), "grandchild survived delete"
