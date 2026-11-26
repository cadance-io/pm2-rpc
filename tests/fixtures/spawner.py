"""Fixture that spawns a grandchild `sleep` and writes its pid to $CHILD_PID_FILE."""

import os
import pathlib
import subprocess
import time

if __name__ == "__main__":
    child = subprocess.Popen(["sleep", "1000"])
    pathlib.Path(os.environ["CHILD_PID_FILE"]).write_text(str(child.pid))
    while True:
        time.sleep(3600)
