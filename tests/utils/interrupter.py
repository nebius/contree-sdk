import os
import signal
import sys
import threading
import time
from contextlib import contextmanager


def _keyboard_interrupt_win():
    """Windows-specific: inject KeyboardInterrupt"""
    import ctypes

    main_thread_id = threading.main_thread().ident
    assert main_thread_id is not None  # noqa: S101
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(main_thread_id), ctypes.py_object(KeyboardInterrupt))


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
