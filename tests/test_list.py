"""pm2_rpc.list() returns dicts; pm2_rpc.exists(name) is the bool form."""

from __future__ import annotations

import pm2_rpc as pm2


def test_list_returns_list_of_dicts(running_fixture: str) -> None:
    procs = pm2.list()
    assert isinstance(procs, list)
    assert all(isinstance(p, dict) for p in procs)
    names = [p["pm2_env"]["name"] for p in procs]
    assert running_fixture in names


def test_exists_true_for_registered(running_fixture: str) -> None:
    assert pm2.exists(running_fixture) is True


def test_exists_false_for_unregistered() -> None:
    assert pm2.exists("definitely-not-a-real-pm2-process-xyz") is False
