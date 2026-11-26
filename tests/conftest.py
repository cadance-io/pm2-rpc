"""Shared pytest helpers for tests that need throwaway PM2 processes.

Fixture processes are spawned via the library's own `pm2.start()` over the
RPC socket — no CLI subprocess. Test names are prefixed `pm2rpc-test-` so
they're easy to spot and clean up if a test crashes mid-run.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

import pm2_rpc as pm2

FIXTURES = Path(__file__).parent / "fixtures"
SLEEPER = FIXTURES / "sleeper.py"
SPAWNER = FIXTURES / "spawner.py"
TEST_PREFIX = "pm2rpc-test-"


def unique_name() -> str:
    return TEST_PREFIX + uuid.uuid4().hex[:8]


def _safe_delete(name: str) -> None:
    try:
        pm2.delete(name)
    except pm2.NotFound:
        pass


@pytest.fixture
def fixture_name() -> str:
    """A unique throwaway process name; cleaned up after the test."""
    name = unique_name()
    yield name
    _safe_delete(name)


@pytest.fixture
def running_fixture() -> str:
    """An already-spawned sleeper. Yields its name; cleaned up after."""
    name = unique_name()
    pm2.start(str(SLEEPER), name=name, autorestart=False)
    try:
        yield name
    finally:
        _safe_delete(name)


@pytest.fixture(scope="session")
def pm2_root() -> Path:
    """The pm2 package dir: $PM2_ROOT, else the global npm install."""
    if "PM2_ROOT" in os.environ:
        root = Path(os.environ["PM2_ROOT"])
    else:
        npm_root = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, check=True
        ).stdout.strip()
        root = Path(npm_root) / "pm2"
    if not (root / "lib" / "Daemon.js").is_file():
        pytest.fail(f"pm2 package not found at {root}; set PM2_ROOT")
    return root
