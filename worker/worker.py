import logging
import threading
from consumer import _run_main_consumer, _run_dlq_consumer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    t1 = threading.Thread(target=_run_main_consumer, daemon=True)
    t2 = threading.Thread(target=_run_dlq_consumer, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == "__main__":
    main()
