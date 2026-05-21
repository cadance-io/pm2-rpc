"""TDD: pm2.restart(target) bumps restart_time. With env=, the merged keys
land in pm2_env.env and the process's actual environment. With update_env=True,
the current shell environment is merged."""

from __future__ import annotations

import os
import time

import pm2


def test_restart_increments_restart_time(running_fixture: str) -> None:
    before = pm2.describe(running_fixture).restart_time
    pm2.restart(running_fixture)
    after = pm2.describe(running_fixture).restart_time
    assert after == before + 1


def test_restart_returns_online_process(running_fixture: str) -> None:
    proc = pm2.restart(running_fixture)
    assert isinstance(proc, pm2.Process)
    assert proc.name == running_fixture
    assert proc.status == "online"
    assert proc.pid is not None and proc.pid > 0


def test_restart_with_env_merges_into_pm2_env(running_fixture: str) -> None:
    pm2.restart(running_fixture, env={"CADANCE_TEST_SERVER_MODE": "suite"})
    pm2_env = pm2.describe(running_fixture).pm2_env
    assert pm2_env["env"]["CADANCE_TEST_SERVER_MODE"] == "suite"


def test_restart_with_update_env_pulls_in_shell_env(
    running_fixture: str, monkeypatch
) -> None:
    key = "PM2RPC_TEST_FLAG"
    monkeypatch.setenv(key, "from-shell")
    pm2.restart(running_fixture, update_env=True)
    pm2_env = pm2.describe(running_fixture).pm2_env
    assert pm2_env["env"][key] == "from-shell"


def test_restart_raises_for_unknown() -> None:
    import pytest
    with pytest.raises(pm2.NotFound):
        pm2.restart("definitely-not-a-real-pm2-process-xyz")
