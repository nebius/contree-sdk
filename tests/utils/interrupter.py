import os
import signal
import sys
import threading
import time
from contextlib import contextmanager

import pytest


@contextmanager
def interrupter(sleep_time: float):
    if sys.platform == "win32":
        pytest.skip("Cannot interrupt blocking I/O operations on Windows")
    old_handler = signal.getsignal(signal.SIGINT)

    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)

        def _interrupter():
            time.sleep(sleep_time)
            os.kill(os.getpid(), signal.SIGINT)

        t = threading.Thread(target=_interrupter, daemon=True)
        t.start()

        yield
    finally:
        signal.signal(signal.SIGINT, old_handler)
