"""TDD: pm2.list() returns Process objects for every daemon-managed app;
pm2.exists(name) is True iff that name is registered."""

from __future__ import annotations

import pm2


def test_list_returns_iterable_of_processes(running_fixture: str) -> None:
    procs = pm2.list()
    assert isinstance(procs, list)
    assert all(isinstance(p, pm2.Process) for p in procs)
    names = [p.name for p in procs]
    assert running_fixture in names


def test_exists_true_for_registered(running_fixture: str) -> None:
    assert pm2.exists(running_fixture) is True


def test_exists_false_for_unregistered() -> None:
    assert pm2.exists("definitely-not-a-real-pm2-process-xyz") is False
