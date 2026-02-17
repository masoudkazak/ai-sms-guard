import os
import subprocess

from watchfiles import run_process


def _run_worker() -> None:
    subprocess.run(["python", "worker.py"], check=False)


if __name__ == "__main__":
    watch_path = os.environ.get("WATCH_PATH", "/app")
    run_process(watch_path, target=_run_worker)
