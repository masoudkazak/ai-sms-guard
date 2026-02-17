import subprocess

from watchfiles import run_process

from env import WATCH_PATH


def _run_worker() -> None:
    subprocess.run(["python", "worker.py"], check=False)


if __name__ == "__main__":
    run_process(WATCH_PATH, target=_run_worker)
