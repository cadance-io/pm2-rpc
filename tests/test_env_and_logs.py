"""env() reads the merged env dict; logs()/error_logs() tail the on-disk file."""

from __future__ import annotations

import time

import pytest

import pm2_rpc as pm2


def test_env_returns_dict_with_expected_keys(running_fixture: str) -> None:
    env = pm2.env(running_fixture)
    assert isinstance(env, dict)
    # PM2 always seeds PATH (or HOME) into the env when fork-spawning
    assert any(k in env for k in ("PATH", "HOME"))


def test_env_reflects_merged_env_after_restart(running_fixture: str) -> None:
    pm2.restart(running_fixture, env={"APP_MODE": "suite"})
    assert pm2.env(running_fixture)["APP_MODE"] == "suite"


def test_env_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.env("definitely-not-a-real-pm2-process-xyz")


def test_logs_returns_recent_stdout_lines(running_fixture: str) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        out = pm2.logs(running_fixture, lines=10)
        if "sleeper started" in out:
            return
        time.sleep(0.1)
    pytest.fail(f"expected 'sleeper started' in stdout logs; got: {out!r}")


def test_logs_lines_truncates(running_fixture: str) -> None:
    # Cause several restarts so multiple "sleeper started" lines accumulate
    for _ in range(3):
        pm2.restart(running_fixture)
    time.sleep(0.3)
    assert pm2.logs(running_fixture, lines=1).count("\n") <= 1


def test_logs_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.logs("definitely-not-a-real-pm2-process-xyz", lines=5)


def test_error_logs_is_separate_function(running_fixture: str) -> None:
    """error_logs reads pm_err_log_path; if nothing failed, expect empty."""
    out = pm2.error_logs(running_fixture, lines=5)
    assert isinstance(out, str)
