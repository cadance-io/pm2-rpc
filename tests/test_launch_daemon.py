"""launch_daemon starts an isolated God daemon under a fresh PM2_HOME.

Each test runs the library in a subprocess, because PM2_HOME is read at
import time. The daemon is killed at the end, whatever the outcome.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from pm2_rpc import PM2Error, _client
from tests.conftest import SLEEPER

_CHILD = """
import json, sys, pathlib
import pm2_rpc as pm2
root = pathlib.Path(sys.argv[1])
pm2.launch_daemon(root)
pm2.launch_daemon(root)
proc = pm2.start(sys.argv[2], name="pm2rpc-test-launch", autorestart=False)
print(json.dumps({
    "sock": str(pm2.SOCK_PATH),
    "ping": pm2.rpc_call("ping"),
    "out_log": proc["pm2_env"]["pm_out_log_path"],
}))
"""


@pytest.fixture
def fresh_home() -> Iterator[Path]:
    # A short path: a Unix socket path must stay under 108 bytes.
    home = Path(tempfile.mkdtemp(prefix="pm2h-", dir="/tmp"))
    yield home
    pid_file = home / "pm2.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text())
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.kill(pid, signal.SIGKILL)
    shutil.rmtree(home, ignore_errors=True)


def test_launch_daemon_serves_rpc_under_pm2_home(fresh_home: Path, pm2_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CHILD, str(pm2_root), str(SLEEPER)],
        env={**os.environ, "PM2_HOME": str(fresh_home)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)

    assert out["sock"] == str(fresh_home / "rpc.sock")
    assert out["ping"] == [{"msg": "pong"}]
    assert out["out_log"] == str(fresh_home / "logs" / "pm2rpc-test-launch-out.log")
    assert (fresh_home / "module_conf.json").read_text() == "{}"
    daemon_pid = int((fresh_home / "pm2.pid").read_text())
    daemon_env = Path(f"/proc/{daemon_pid}/environ").read_bytes().split(b"\0")
    assert f"_={pm2_root / 'bin' / 'pm2'}".encode() in daemon_env


@pytest.fixture
def no_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the library at an empty PM2_HOME where nothing answers ping."""
    monkeypatch.setattr(_client.axon, "PM2_HOME", tmp_path)
    monkeypatch.setattr(_client.axon, "SOCK_PATH", tmp_path / "rpc.sock")
    return tmp_path


def test_launch_daemon_missing_entrypoint_raises(no_daemon: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"Daemon\.js"):
        _client.launch_daemon(no_daemon / "not-pm2")


def test_launch_daemon_reports_a_daemon_that_exits(no_daemon: Path) -> None:
    fake_root = no_daemon / "fake-pm2"
    (fake_root / "lib").mkdir(parents=True)
    (fake_root / "lib" / "Daemon.js").write_text("console.error('boom'); process.exit(3)")
    with pytest.raises(PM2Error, match="exited with code 3"):
        _client.launch_daemon(fake_root)
    assert "boom" in (no_daemon / "pm2.log").read_text()


def test_launch_daemon_times_out_when_ping_never_answers(no_daemon: Path) -> None:
    fake_root = no_daemon / "fake-pm2"
    (fake_root / "lib").mkdir(parents=True)
    (fake_root / "lib" / "Daemon.js").write_text("setTimeout(() => {}, 5000)")
    with pytest.raises(TimeoutError, match="did not answer ping within"):
        _client.launch_daemon(fake_root, timeout=0.5)
