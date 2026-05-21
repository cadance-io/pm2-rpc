# pm2-rpc

Pure-Python client for [PM2](https://pm2.keymetrics.io/)'s daemon RPC socket.

> [!CAUTION]
> **Experimental (v0.1.0)** — Early-stage personal project. The API will change without notice.

Talks directly to the `~/.pm2/rpc.sock` Unix socket using PM2's
`pm2-axon` / `pm2-axon-rpc` wire stack (AMP framing -> amp-message arg
packing -> axon-rpc body). No `pm2` CLI shell-out for the common cases.

## Quick Start

```python
import pm2

for p in pm2.list():
    print(p.pm_id, p.name, p.status)

pm2.stop("worker")
pm2.delete("worker")
```

## Installation

```bash
pip install pm2-rpc
```

Requires Python >= 3.12 and a running PM2 daemon on the same host.

## Development

```bash
uv sync --group dev
uv run pytest tests/        # requires a real PM2 daemon
```

## License

MIT — see [`LICENSE`](LICENSE).
