import os
import signal
import threading
import time
from contextlib import contextmanager


@contextmanager
def interrupter(sleep_time: float):
    old_handler = signal.getsignal(signal.SIGINT)

    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)

        def _interrupter():
            time.sleep(sleep_time)
            os.kill(os.getpid(), signal.SIGINT)

        t = threading.Thread(target=_interrupter)
        t.start()

        yield
    finally:
        signal.signal(signal.SIGINT, old_handler)
