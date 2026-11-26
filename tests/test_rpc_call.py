"""rpc_call sends `{}` when the caller passes no argument."""

from __future__ import annotations

import pm2_rpc as pm2


def test_rpc_call_without_args_does_not_crash_daemon() -> None:
    assert pm2.rpc_call("ping") == pm2.rpc_call("ping", {})
    assert isinstance(pm2.list(), list)
