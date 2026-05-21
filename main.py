"""Demo: walk through the CADANCE_TEST_SERVER_MODE flip workflow.

Mirrors the CLI flow:
    pm2 describe <name>                    # existence probe
    pm2 start ecosystem.config.js --only X # bootstrap if missing
    pm2 env <id>                           # check current mode
    pm2 restart <name> --update-env        # flip the mode
    pm2 logs <name> --lines N --nostream   # peek on failure
    pm2 stop <name>                        # teardown
"""

from __future__ import annotations

import axon
import pm2


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def show_list() -> None:
    procs = pm2.list()
    print(f"PM2 processes ({len(procs)}):\n")
    header = f"{'id':>3}  {'name':<30}  {'pid':>7}  {'status':<10}  {'mem':>8}  cpu"
    print(header)
    print("-" * len(header))
    for p in procs:
        monit = p.raw.get("monit", {})
        print(
            f"{p.pm_id:>3}  "
            f"{p.name:<30}  "
            f"{(p.pid or 0):>7}  "
            f"{p.status:<10}  "
            f"{_fmt_bytes(monit.get('memory') or 0):>8}  "
            f"{(monit.get('cpu') or 0):>3}%"
        )


def ensure_suite_mode(name: str, ecosystem: str) -> None:
    """Make sure `name` is running with CADANCE_TEST_SERVER_MODE=suite."""
    if not pm2.exists(name):
        print(f"[bootstrap] {name} not registered → starting from {ecosystem}")
        pm2.start_ecosystem(ecosystem, only=name)
        return

    current = pm2.env(name).get("CADANCE_TEST_SERVER_MODE")
    if current == "suite":
        print(f"[skip] {name} already in suite mode")
        return

    print(f"[flip] {name} mode {current!r} → 'suite'")
    try:
        pm2.restart(name, env={"CADANCE_TEST_SERVER_MODE": "suite"})
    except axon.PM2Error:
        print(f"[error] restart failed — last logs:\n{pm2.logs(name, lines=20)}")
        raise


if __name__ == "__main__":
    show_list()
