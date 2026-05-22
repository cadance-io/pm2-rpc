"""TDD: pm2.start(script, name=, ...) launches a process via pure socket RPC."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import pm2
from tests.conftest import SLEEPER, unique_name


@pytest.fixture
def started_name() -> str:
    """Yield a unique name; ensure cleanup even if the test fails."""
    name = unique_name()
    yield name
    try:
        pm2.delete(name)
    except pm2.NotFound:
        pass


def test_start_returns_online_process(started_name: str) -> None:
    proc = pm2.start(str(SLEEPER), name=started_name)
    assert isinstance(proc, pm2.Process)
    assert proc.name == started_name
    assert proc.status == "online"
    assert proc.pid is not None and proc.pid > 0


def test_start_registers_in_list(started_name: str) -> None:
    pm2.start(str(SLEEPER), name=started_name)
    assert pm2.exists(started_name)


def test_start_passes_env_to_process(started_name: str) -> None:
    pm2.start(
        str(SLEEPER), name=started_name, env={"APP_MODE": "suite", "FOO": "bar"}
    )
    env = pm2.env(started_name)
    assert env["APP_MODE"] == "suite"
    assert env["FOO"] == "bar"


def test_start_writes_to_log(started_name: str) -> None:
    pm2.start(str(SLEEPER), name=started_name)
    # sleeper prints one line on startup; give PM2 a moment to flush
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if "sleeper started" in pm2.logs(started_name, lines=5):
            return
        time.sleep(0.1)
    pytest.fail("expected startup line in logs within 3s")


def test_start_name_defaults_to_script_stem(tmp_path: Path) -> None:
    # Copy sleeper to a unique stem so we don't collide
    name = unique_name()
    script = tmp_path / f"{name}.py"
    script.write_text(SLEEPER.read_text())
    try:
        proc = pm2.start(str(script))
        assert proc.name == name
    finally:
        try:
            pm2.delete(name)
        except pm2.NotFound:
            pass


def test_start_missing_script_raises(started_name: str) -> None:
    with pytest.raises(FileNotFoundError):
        pm2.start("/no/such/file.py", name=started_name)
