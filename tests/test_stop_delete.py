"""TDD:
  * pm2.stop(target) gracefully stops but KEEPS the entry (status='stopped')
  * pm2.delete(target) removes the entry entirely
"""

from __future__ import annotations

import pytest

import pm2


def test_stop_keeps_entry_with_stopped_status(running_fixture: str) -> None:
    pm2.stop(running_fixture)
    p = pm2.describe(running_fixture)
    assert p.status == "stopped"
    assert p.pid is None


def test_stop_returns_process(running_fixture: str) -> None:
    p = pm2.stop(running_fixture)
    assert isinstance(p, pm2.Process)
    assert p.name == running_fixture


def test_delete_removes_entry(running_fixture: str) -> None:
    pm2.delete(running_fixture)
    assert pm2.exists(running_fixture) is False
    with pytest.raises(pm2.NotFound):
        pm2.describe(running_fixture)


def test_delete_raises_for_unknown() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.delete("definitely-not-a-real-pm2-process-xyz")
