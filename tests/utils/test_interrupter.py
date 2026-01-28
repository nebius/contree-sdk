import time

import pytest

from tests.utils.interrupter import interrupter


def test_sleep_interrupted_by_interrupter():
    start = time.time()
    with interrupter(0.1):
        with pytest.raises(KeyboardInterrupt):
            time.sleep(10)
        elapsed = time.time() - start
    assert elapsed < 1.0
