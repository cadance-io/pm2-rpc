"""TDD:
  * pm2.env(target) returns the merged env dict the process actually sees.
  * pm2.logs(target, lines=N) returns the last N lines of stdout (or stderr).
"""

from __future__ import annotations

import time

import pytest

import pm2


def test_env_returns_dict_with_expected_keys(running_fixture: str) -> None:
    env = pm2.env(running_fixture)
    assert isinstance(env, dict)
    # PM2 always seeds PATH (or HOME) into the env when fork-spawning
    assert any(k in env for k in ("PATH", "HOME"))


def test_env_reflects_merged_env_after_restart(running_fixture: str) -> None:
    pm2.restart(running_fixture, env={"APP_MODE": "suite"})
    env = pm2.env(running_fixture)
    assert env["APP_MODE"] == "suite"


def test_env_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.env("definitely-not-a-real-pm2-process-xyz")


def test_logs_returns_last_n_stdout_lines(running_fixture: str) -> None:
    # Sleeper prints one line at startup; give PM2 a moment to flush
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        logs = pm2.logs(running_fixture, lines=10)
        if "sleeper started" in logs:
            return
        time.sleep(0.1)
    pytest.fail(f"expected 'sleeper started' in logs; got: {logs!r}")


def test_logs_lines_argument_truncates(running_fixture: str) -> None:
    # Cause several restarts so multiple "sleeper started" lines accumulate
    for _ in range(3):
        pm2.restart(running_fixture)
    time.sleep(0.3)
    one_line = pm2.logs(running_fixture, lines=1)
    assert one_line.count("\n") <= 1  # at most one newline → at most one line


def test_logs_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.logs("definitely-not-a-real-pm2-process-xyz", lines=5)
