# pm2-rpc

Pure-Python client for [PM2](https://pm2.keymetrics.io/)'s daemon RPC socket.

> [!CAUTION]
> **Experimental (v0.3.0)** — Early-stage personal project. API may change without notice.

Talks directly to `$PM2_HOME/rpc.sock` (default `~/.pm2/rpc.sock`) using PM2's `pm2-axon` / `pm2-axon-rpc`
wire stack (AMP framing → amp-message arg packing → axon-rpc body). The
runtime makes **zero `pm2` CLI subprocess calls** — every operation is one
round-trip on the Unix socket. Returned values are plain dicts in PM2's
own shape, no extra abstraction.

## Install

```bash
pip install pm2-rpc           # core (only stdlib)
pip install 'pm2-rpc[yaml]'   # add YAML ecosystem-config support
```

Requires Python ≥ 3.11 and PM2 installed on the same host. `launch_daemon()` starts
the daemon if none runs. `PM2_HOME` is read once, at import.

## Quick start

```python
import os
import pm2_rpc as pm2

# List
for p in pm2.list():
    env = p["pm2_env"]
    print(env["pm_id"], env["name"], env["status"])

# Describe (raises pm2.NotFound)
proc = pm2.describe("worker")
print(proc["pm2_env"]["restart_time"])

# Start a fresh process — no ecosystem file required
pm2.start("scripts/worker.py", name="worker", env={"DEBUG": "1"})

# Lifecycle knobs for apps with awkward shutdown / file-watch needs:
pm2.start("dev_server.py", name="api", kill_timeout=10000)       # 10s window
pm2.start("notebook.py", name="nb", kill_signal="SIGINT")         # jupyter-style
pm2.start("worker.py", name="w", watch=["src", "config.yaml"])   # PM2-managed reload

# Daemon-side fields, and the shell env filter pm2 applies before `env`:
pm2.start("worker.py", name="w", namespace="lane1", watch=["src"], ignore_watch=["node_modules"])
pm2.start("server.py", name="s", wait_ready=True, listen_timeout=8000)
pm2.start("app.py", name="a", filter_env=["DATABASE_"], env={"DATABASE_URL": "..."})
pm2.start("npm", name="web", args="run dev")   # bare names resolve on $PATH

# Start the God daemon if none answers ping (pass the pm2 package dir)
from pathlib import Path
pm2.launch_daemon(Path("/usr/lib/node_modules/pm2"))

# Or from an ecosystem.config.{json,yaml}
pm2.start_ecosystem("ecosystem.config.json", only="worker")

# Flip an env var without re-reading the ecosystem file (avoids the
# `pm2 restart NAME --update-env` foot-gun where passing ecosystem.config.js
# silently overrides --update-env)
pm2.restart("worker", env={**os.environ, "APP_MODE": "suite"})

# Logs (tails the file PM2 writes on disk, no streaming)
print(pm2.logs("worker", lines=50))
print(pm2.error_logs("worker", lines=20))

# Teardown
pm2.stop("worker")    # keeps the entry, status='stopped'
pm2.delete("worker")  # removes it entirely
```

## API

| | |
|---|---|
| `list() -> list[dict]` | All registered processes |
| `exists(name) -> bool` | Cheap existence probe |
| `describe(target) -> dict` | One process; raises `NotFound` |
| `start(script, **opts) -> dict` | Launch (fork mode); see kwargs below |
| `start_ecosystem(config, *, only=, cwd=) -> list[dict]` | `.json`/`.yaml`; `.js` or an unknown app key raises `UnsupportedConfigError` |
| `launch_daemon(pm2_root, *, node="node", timeout=10.0) -> None` | Start the daemon under `PM2_HOME` unless one answers ping |
| `restart(target, *, env=None) -> dict` | `env` merges server-side via Object.assign |
| `stop(target) -> dict` | Graceful stop, keeps entry |
| `delete(target) -> None` | Unregister |
| `env(target) -> dict[str, str]` | The runtime env the process sees |
| `logs(target, lines=15) -> str` | Last N lines of stdout |
| `error_logs(target, lines=15) -> str` | Last N lines of stderr |

`pm2_rpc.start()` kwargs use PM2's vocabulary: `name`, `interpreter`, `cwd`,
`args`, `env`, `autorestart`, `out_file`, `error_file`, `merge_logs`,
`kill_timeout`, `kill_signal`, `watch`, `ignore_watch`, `namespace`,
`wait_ready`, `listen_timeout`, `filter_env`. `filter_env=True` drops the
whole shell env, a string drops the one var of that name, and a list drops
each var whose name contains an item. `env` then merges on top.

Each app gets the defaults the pm2 CLI sets and the daemon reads:
`treekill: true` (so `stop`/`delete` kill grandchildren too),
`merge_logs: true`, `autostart: true`, `instance_var: NODE_APP_INSTANCE`,
and `PWD=cwd` in the app env. `pm2_rpc.restart()` additionally
accepts `kill_timeout` to bump the graceful-shutdown window for the next stop.

Low-level access if you need it:

```python
from pm2_rpc import rpc_call, PM2Error
rpc_call("getMonitorData", {})   # raw axon-rpc round-trip
```

## What's not supported (v0.3.0)

- Cluster mode (`exec_mode: "cluster"`, `instances > 1`) — fork-mode only.
- `.js`/`.cjs`/`.mjs` ecosystem configs (require node to evaluate
  `module.exports`). Convert to `.json`/`.yaml`, use `pm2_rpc.start()` with
  app fields, or shell out to `pm2 start ecosystem.config.js --only NAME`.
- NVM-pinned interpreters (`exec_interpreter: "node@18.0.0"`).
- Source-map auto-detection.
- Log follow, `save`/dump, `startup`.

## Development

```bash
uv sync --group dev
uv run pytest tests/        # ~100 tests, ~8s, requires a live PM2 daemon
uv run ruff check           # lint
uv run ruff format          # format (omit --check to apply)
uv run mypy                 # typecheck pm2_rpc/
```

Run the suite against a throwaway daemon, not your own:
`PM2_HOME=/tmp/pm2-test uv run python -c "import pm2_rpc, pathlib; pm2_rpc.launch_daemon(pathlib.Path('$(npm root -g)/pm2'))"`,
then `PM2_HOME=/tmp/pm2-test uv run pytest`. The `launch_daemon` tests find
pm2 through `$PM2_ROOT`, else `npm root -g`.

CI runs lint + format + typecheck + the full test suite + build on every
PR — PM2 is installed from npm on the runner.

Fixture processes are named `pm2rpc-test-*` so they're easy to identify
if a test crashes and leaks one.

## License

MIT — see [`LICENSE`](LICENSE).
