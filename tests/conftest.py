"""Shared pytest helpers for tests that need throwaway PM2 processes.

Fixture processes are spawned via the library's own `pm2.start()` over the
RPC socket — no CLI subprocess. Test names are prefixed `pm2rpc-test-` so
they're easy to spot and clean up if a test crashes mid-run.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import pm2_rpc as pm2

FIXTURES = Path(__file__).parent / "fixtures"
SLEEPER = FIXTURES / "sleeper.py"
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
