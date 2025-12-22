import asyncio
from asyncio import AbstractEventLoop
from collections.abc import AsyncIterable, Awaitable, Callable, Iterator
from concurrent.futures import Future
from functools import wraps
from threading import Event, Lock, Thread
from typing import ParamSpec, TypeVar


P = ParamSpec("P")
T = TypeVar("T")
Y = TypeVar("Y")


def _on_task_done(future: Future, task: asyncio.Task):
    if task.exception():
        future.set_exception(task.exception())
    else:
        future.set_result(task.result())


class _WrapperContext:
    def __init__(self):
        self.thread: Thread | None = None
        self.futures: set[Future] = set()
        self._loop: AbstractEventLoop | None = None
        self._lock: Lock = Lock()
        self._start_event: Event = Event()

    def ensure_running(self):
        with self._lock:
            if self._loop is not None:
                return
            self._start_event.clear()
            self.thread = Thread(target=self._thread_main, daemon=True)
            self.thread.start()
            self._start_event.wait()

    @property
    def loop(self):
        self.ensure_running()
        return self._loop

    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        self._start_event.set()
        self.loop.run_forever()

    def _close(self):
        with self._lock:
            if self._loop is not None:
                self._loop.close()
                self._loop = None
            self.thread = None

    def close(self):
        for future in self.futures:
            future.cancel()
        self._loop.call_soon_threadsafe(self._close)

    def __del__(self):
        self.close()


class AsyncWrapper:
    _shared_context: _WrapperContext = _WrapperContext()

    def __init__(self, is_global: bool = True):
        self._is_global = is_global
        if self._is_global:
            self._context = self._shared_context
        else:
            self._context = _WrapperContext()

    def _coro_to_future(self, coro: Awaitable[T]) -> Future:
        future = asyncio.run_coroutine_threadsafe(coro, self._context.loop)
        self._context.futures.add(future)
        return future

    def decorator(self, func: Callable[P, Awaitable[T]]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return self.wrap(func(*args, **kwargs))

        return wrapper

    def wrap(self, coro: Awaitable[T]) -> T:
        future = self._coro_to_future(coro)
        try:
            return future.result()
        except (KeyboardInterrupt, StopAsyncIteration):
            future.cancel()
            raise

    def wrap_iter(self, coro_iter: AsyncIterable[Y]) -> Iterator[Y]:
        async_iter = coro_iter.__aiter__()
        while True:
            try:
                yield self.wrap(async_iter.__anext__())
            except StopAsyncIteration:
                return


def to_sync(func: Callable[P, Awaitable[T]]) -> Callable[P, T]:
    wrapper = AsyncWrapper()
    return wrapper.decorator(func)


def coro_sync(coro: Awaitable[T]) -> T:
    wrapper = AsyncWrapper()
    return wrapper.wrap(coro)


def coro_iter_sync(coro_iter: AsyncIterable[Y]) -> Iterator[Y]:
    wrapper = AsyncWrapper()
    return wrapper.wrap_iter(coro_iter)
