"""TDD: pm2.describe(target) returns a Process for a name OR pm_id;
       raises NotFound otherwise."""

from __future__ import annotations

import pytest

import pm2


def test_describe_by_name(running_fixture: str) -> None:
    p = pm2.describe(running_fixture)
    assert isinstance(p, pm2.Process)
    assert p.name == running_fixture
    assert p.status == "online"
    assert isinstance(p.pid, int) and p.pid > 0


def test_describe_by_pm_id(running_fixture: str) -> None:
    by_name = pm2.describe(running_fixture)
    by_id = pm2.describe(by_name.pm_id)
    assert by_id.name == running_fixture
    assert by_id.pm_id == by_name.pm_id


def test_describe_raises_for_unknown_name() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.describe("definitely-not-a-real-pm2-process-xyz")


def test_describe_raises_for_unknown_id() -> None:
    with pytest.raises(pm2.NotFound):
        pm2.describe(99999)
