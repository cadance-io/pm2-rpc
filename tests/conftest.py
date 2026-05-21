"""Shared pytest helpers for tests that need throwaway PM2 processes.

Uses the `pm2` CLI to bootstrap fixture processes (so we don't depend on
the code-under-test for setup). Test names are prefixed `pm2rpc-test-` so
they're easy to spot and clean up if a test crashes mid-run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SLEEPER = FIXTURES / "sleeper.py"
TEST_PREFIX = "pm2rpc-test-"


def _pm2(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    pm2 = shutil.which("pm2")
    if pm2 is None:
        pytest.skip("pm2 CLI not on PATH")
    return subprocess.run(
        [pm2, *args],
        capture_output=True,
        text=True,
        check=check,
    )


def cli_start(name: str) -> None:
    """Spawn a sleeper process named `name` via the pm2 CLI."""
    _pm2(
        "start", str(SLEEPER),
        "--name", name,
        "--interpreter", sys.executable,
        "--no-autorestart",
    )
    # PM2 returns from the CLI before the process is fully online in some cases.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        r = _pm2("jlist", check=False)
        if r.returncode == 0 and name in r.stdout:
            return
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for fixture process {name!r} to register")


def cli_delete(name: str) -> None:
    _pm2("delete", name, check=False)


def unique_name() -> str:
    return TEST_PREFIX + uuid.uuid4().hex[:8]


@pytest.fixture
def fixture_name() -> str:
    """A unique throwaway process name; cleaned up via CLI after the test."""
    name = unique_name()
    yield name
    cli_delete(name)


@pytest.fixture
def running_fixture() -> str:
    """An already-spawned sleeper. Yields its name; cleaned up after."""
    name = unique_name()
    cli_start(name)
    try:
        yield name
    finally:
        cli_delete(name)
