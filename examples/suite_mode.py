"""Example: ensure a long-running PM2 app is up with APP_MODE=suite.

Mirrors the CLI flow:
    pm2 describe <name>                    # existence probe
    pm2 start ecosystem.config.json --only X  # bootstrap if missing
    pm2 env <id>                           # check current mode
    pm2 restart <name>                     # flip the mode (env merges server-side)
    pm2 logs <name> --lines N --nostream   # peek on failure
    pm2 stop <name>                        # teardown (not shown here)
"""

from __future__ import annotations

import os

import pm2_rpc as pm2


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
        env = p["pm2_env"]
        monit = p.get("monit", {})
        print(
            f"{env['pm_id']:>3}  "
            f"{env['name']:<30}  "
            f"{(p.get('pid') or 0):>7}  "
            f"{env['status']:<10}  "
            f"{_fmt_bytes(monit.get('memory') or 0):>8}  "
            f"{(monit.get('cpu') or 0):>3}%"
        )


def ensure_suite_mode(name: str, ecosystem: str) -> None:
    """Make sure `name` is running with APP_MODE=suite."""
    if not pm2.exists(name):
        print(f"[bootstrap] {name} not registered → starting from {ecosystem}")
        pm2.start_ecosystem(ecosystem, only=name)
        return

    if pm2.env(name).get("APP_MODE") == "suite":
        print(f"[skip] {name} already in suite mode")
        return

    print(f"[flip] {name} → APP_MODE=suite")
    try:
        pm2.restart(name, env={**os.environ, "APP_MODE": "suite"})
    except pm2.PM2Error:
        print(f"[error] restart failed — last stderr:\n{pm2.error_logs(name, lines=20)}")
        raise


if __name__ == "__main__":
    show_list()
