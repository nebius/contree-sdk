import os
import signal
import sys
import threading
import time
from contextlib import contextmanager


def _keyboard_interrupt_win():
    """Windows-specific: send CTRL_C_EVENT to process group"""
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[reportAttributeAccessIssue]
    # CTRL_C_EVENT = 0 # noqa: ERA001
    kernel32.GenerateConsoleCtrlEvent(0, 0)


def _keyboard_interrupt_unix():
    """Unix-specific: send SIGINT signal"""
    os.kill(os.getpid(), signal.SIGINT)


@contextmanager
def interrupter(sleep_time: float):
    old_handler = signal.getsignal(signal.SIGINT)

    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)

        def _interrupter():
            time.sleep(sleep_time)
            if sys.platform == "win32":
                _keyboard_interrupt_win()
            else:
                _keyboard_interrupt_unix()

        t = threading.Thread(target=_interrupter, daemon=True)
        t.start()

        yield
    finally:
        signal.signal(signal.SIGINT, old_handler)
