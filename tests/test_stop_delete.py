"""stop() keeps the entry registered (status='stopped'); delete() removes it."""

from __future__ import annotations

import time

import pytest

import pm2_rpc as pm2
from tests.conftest import FIXTURES

STUBBORN = str(FIXTURES / "stubborn.py")


def test_stop_keeps_entry_with_stopped_status(running_fixture: str) -> None:
    pm2.stop(running_fixture)
    p = pm2.describe(running_fixture)
    assert p["pm2_env"]["status"] == "stopped"
    # PM2 sets pid to 0 on stop; treat falsy as "not running"
    assert not p.get("pid")


def test_stop_returns_dict(running_fixture: str) -> None:
    p = pm2.stop(running_fixture)
    assert isinstance(p, dict)
    assert p["pm2_env"]["name"] == running_fixture


def test_delete_removes_entry(running_fixture: str) -> None:
    pm2.delete(running_fixture)
    assert pm2.exists(running_fixture) is False
    with pytest.raises(pm2.NotFound):
        pm2.describe(running_fixture)


def test_delete_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.delete("definitely-not-a-real-pm2-process-xyz")


def test_delete_waits_out_a_kill_timeout_above_ten_seconds(fixture_name: str) -> None:
    pm2.start(STUBBORN, name=fixture_name, autorestart=False, kill_timeout=11000)
    started = time.monotonic()
    pm2.delete(fixture_name)
    assert time.monotonic() - started >= 11
    assert pm2.exists(fixture_name) is False


def test_stop_waits_out_a_kill_timeout_above_ten_seconds(fixture_name: str) -> None:
    pm2.start(STUBBORN, name=fixture_name, autorestart=False, kill_timeout=11000)
    started = time.monotonic()
    p = pm2.stop(fixture_name)
    assert time.monotonic() - started >= 11
    assert p["pm2_env"]["status"] == "stopped"


def test_delete_raises_timeout_when_the_daemon_outlasts_it(fixture_name: str) -> None:
    pm2.start(STUBBORN, name=fixture_name, autorestart=False, kill_timeout=2000)
    with pytest.raises(TimeoutError):
        pm2.delete(fixture_name, timeout=0.5)
    time.sleep(2.5)
    assert pm2.exists(fixture_name) is False
