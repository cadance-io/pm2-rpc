"""Trivial fixture script PM2 can manage. Sleeps until killed."""

import os
import signal
import time


def _bye(*_):
    raise SystemExit(0)


if __name__ == "__main__":
    print(f"sleeper started pid={os.getpid()}", flush=True)
    signal.signal(signal.SIGTERM, _bye)
    signal.signal(signal.SIGINT, _bye)
    while True:
        time.sleep(3600)
