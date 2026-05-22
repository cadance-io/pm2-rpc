"""restart() bumps restart_time; env= merges keys into the running process."""

from __future__ import annotations

import os

import pytest

import pm2_rpc as pm2


def test_restart_increments_restart_time(running_fixture: str) -> None:
    before = pm2.describe(running_fixture)["pm2_env"]["restart_time"]
    pm2.restart(running_fixture)
    after = pm2.describe(running_fixture)["pm2_env"]["restart_time"]
    assert after == before + 1


def test_restart_returns_online_dict(running_fixture: str) -> None:
    proc = pm2.restart(running_fixture)
    assert isinstance(proc, dict)
    assert proc["pm2_env"]["name"] == running_fixture
    assert proc["pm2_env"]["status"] == "online"
    assert proc["pid"] > 0


def test_restart_with_env_merges_into_pm2_env(running_fixture: str) -> None:
    pm2.restart(running_fixture, env={"APP_MODE": "suite"})
    env = pm2.describe(running_fixture)["pm2_env"]["env"]
    assert env["APP_MODE"] == "suite"


def test_restart_with_shell_env_splat(running_fixture: str, monkeypatch) -> None:
    """The old `update_env=True` flag is gone; callers do this explicitly."""
    monkeypatch.setenv("PM2RPC_TEST_FLAG", "from-shell")
    pm2.restart(running_fixture, env={**os.environ})
    env = pm2.describe(running_fixture)["pm2_env"]["env"]
    assert env["PM2RPC_TEST_FLAG"] == "from-shell"


def test_restart_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.restart("definitely-not-a-real-pm2-process-xyz")
