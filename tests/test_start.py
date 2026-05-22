"""pm2_rpc.start(script, name=, ...) launches via the prepare RPC."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import pm2_rpc as pm2
from tests.conftest import SLEEPER, fixture_name as fixture_name, unique_name  # noqa: F401 (re-export for clarity)


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


def test_start_does_not_fall_back_to_path(fixture_name: str) -> None:
    """`pm2.start('python3')` used to silently find /usr/bin/python3 — gone."""
    with pytest.raises(FileNotFoundError):
        pm2.start("python3", name=fixture_name)
