"""Fixture that ignores PM2's stop signals, so only SIGKILL ends it."""

import os
import signal
import time

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print(f"stubborn started pid={os.getpid()}", flush=True)
    while True:
        time.sleep(3600)
