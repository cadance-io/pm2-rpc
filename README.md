# pm2-rpc

Pure-Python client for [PM2](https://pm2.keymetrics.io/)'s daemon RPC socket.

> [!CAUTION]
> **Experimental (v0.2.0)** — Early-stage personal project. API may change without notice.

Talks directly to `~/.pm2/rpc.sock` using PM2's `pm2-axon` / `pm2-axon-rpc`
wire stack (AMP framing → amp-message arg packing → axon-rpc body). The
runtime makes **zero `pm2` CLI subprocess calls** — every operation is one
round-trip on the Unix socket. Returned values are plain dicts in PM2's
own shape, no extra abstraction.

## Install

```bash
pip install pm2-rpc           # core (only stdlib)
pip install 'pm2-rpc[yaml]'   # add YAML ecosystem-config support
```

Requires Python ≥ 3.12 and a running PM2 daemon on the same host.

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
| `start_ecosystem(config, *, only=, cwd=) -> list[dict]` | `.json`/`.yaml`; `.js` raises `UnsupportedConfigError` |
| `restart(target, *, env=None) -> dict` | `env` merges server-side via Object.assign |
| `stop(target) -> dict` | Graceful stop, keeps entry |
| `delete(target) -> None` | Unregister |
| `env(target) -> dict[str, str]` | The runtime env the process sees |
| `logs(target, lines=15) -> str` | Last N lines of stdout |
| `error_logs(target, lines=15) -> str` | Last N lines of stderr |

`pm2_rpc.start()` kwargs use PM2's vocabulary: `name`, `interpreter`, `cwd`,
`args`, `env`, `autorestart`, `out_file`, `error_file`, `merge_logs`.

Low-level access if you need it:

```python
from pm2_rpc import rpc_call, PM2Error
rpc_call("getMonitorData", {})   # raw axon-rpc round-trip
```

## What's not supported (v0.2.0)

- Cluster mode (`exec_mode: "cluster"`, `instances > 1`) — fork-mode only.
- `.js`/`.cjs`/`.mjs` ecosystem configs (require node to evaluate
  `module.exports`). Convert to `.json`/`.yaml`, use `pm2_rpc.start()` with
  app fields, or shell out to `pm2 start ecosystem.config.js --only NAME`.
- NVM-pinned interpreters (`exec_interpreter: "node@18.0.0"`).
- `filter_env`, source-map auto-detection, watch mode.
- `$PATH` lookup of script names — pass an absolute path (use
  `shutil.which()` yourself if you really want a PATH binary).

## Development

```bash
uv sync --group dev
uv run pytest tests/        # 64 tests, ~6s, requires a live PM2 daemon
uv run ruff check           # lint
uv run ruff format          # format (omit --check to apply)
uv run mypy                 # typecheck pm2_rpc/
```

CI runs lint + format + typecheck + build on every PR (the test suite stays
local because it needs PM2 running).

Fixture processes are named `pm2rpc-test-*` so they're easy to identify
if a test crashes and leaks one.

## License

MIT — see [`LICENSE`](LICENSE).
