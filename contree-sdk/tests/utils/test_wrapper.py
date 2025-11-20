import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Thread

import pytest

from contree_sdk.utils.wrapper import coro_iter_sync, to_sync


_wait_time = 0.01


async def fake_task(a: int, b: int = 1, ex: Exception = None) -> int:
    await asyncio.sleep(_wait_time)
    if ex:
        raise ex
    return a + 2 * b


fake_task_sync = to_sync(fake_task)


def test_basic():
    res = fake_task_sync(3)
    assert res == 5


def test_exception():
    with pytest.raises(RuntimeError):
        fake_task_sync(3, ex=RuntimeError("Some error"))


def test_multiple_threads():
    data = {2, 3, 4, 5, 6}
    threads = []

    def run_task(a, b):
        result = fake_task_sync(a, b)
        data.discard(result)

    started = datetime.now()
    for i in range(5):
        thread = Thread(target=run_task, args=(i, 1))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    spent = datetime.now() - started
    assert spent.total_seconds() <= _wait_time * 1.2 + 0.05

    assert data == set()


def test_thread_pool_executor():
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fake_task_sync, i, 2) for i in range(5)]
        executor_results = [future.result() for future in futures]

    assert len(executor_results) == 5
    assert sorted(executor_results) == [4, 5, 6, 7, 8]


def test_multiple_tasks_in_threads():
    data = {2, 3, 4, 5, 6}
    threads = []

    def run_task(a, b):
        result = fake_task_sync(a, b)
        data.discard(result)

    @to_sync
    async def another_task():
        await asyncio.sleep(_wait_time / 2)

    started = datetime.now()
    for _ in range(50):
        thread = Thread(target=another_task)
        threads.append(thread)
        thread.start()
    for i in range(10):
        thread = Thread(target=run_task, args=(i, 1))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    spent = datetime.now() - started
    assert spent.total_seconds() <= _wait_time * 1.2 + 0.05
    assert data == set()


async def fake_iter(a: int, num: int = 10):
    for i in range(num):
        await asyncio.sleep(_wait_time)
        yield i**a


def test_basic_iter():
    res = []
    started = datetime.now()
    for item in coro_iter_sync(fake_iter(5)):
        spent = datetime.now() - started
        assert spent.total_seconds() <= _wait_time * 1.2
        res.append(item)
        started = datetime.now()
    assert res == [i**5 for i in range(10)]
