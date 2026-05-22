"""stop() keeps the entry registered (status='stopped'); delete() removes it."""

from __future__ import annotations

import pytest

import pm2_rpc as pm2


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
