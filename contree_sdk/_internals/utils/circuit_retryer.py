import logging
from asyncio import FIRST_COMPLETED, Event, Lock, Semaphore, create_task, sleep, wait
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta
from enum import auto
from typing import TypeVar

from strenum import StrEnum


R = TypeVar("R")

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    OPEN = auto()
    CLOSED = auto()
    MIDDLE = auto()


class CircuitRetryer:
    def __init__(
        self,
        exceptions: list[type[Exception]],
        recovery_timeout: timedelta = timedelta(seconds=20),
        external_contexts: list[AbstractAsyncContextManager] | None = None,
    ):
        self.exceptions = exceptions or [Exception]
        self.recovery_threshold = 10
        self.recovery_timeout = recovery_timeout
        self.external_contexts = external_contexts or []

        # state
        self._state_lock = Lock()
        self._failures = 0
        self._successes = 0
        self._last_failure: datetime = datetime.min

        # middle
        self._middle_semaphore = Semaphore()

        # closed
        self._closed_event = Event()  # set, when fully closed
        self._closed_event.set()

        # retries
        self._retry_lock = Lock()
        self.retry_timeout = timedelta(seconds=60)
        self.retry_interval = timedelta(seconds=1)

        # claim
        self._claim_lock = Lock()

    async def _wait_recovery(self):
        while True:
            state = await self._refresh_state()
            if state == CircuitState.CLOSED:
                return
            await sleep(max((self.recovery_timeout - (datetime.now() - self._last_failure)).total_seconds(), 0))

    @asynccontextmanager
    async def _with_retry_lock(self):
        async with self._retry_lock:
            await sleep(self.retry_interval.total_seconds())
            yield

    @asynccontextmanager
    async def _gate(self):
        async with AsyncExitStack() as exit_stack:
            for sem in self.external_contexts:
                await exit_stack.enter_async_context(sem)
            coros = [
                create_task(self._closed_event.wait()),  # if circuit is fully closed
                create_task(self._wait_recovery()),  # if circuit is recovered by time
                create_task(self._middle_semaphore.acquire()),  # if circuit is in middle state, wait for more succeeds
                create_task(
                    exit_stack.enter_async_context(self._with_retry_lock())
                ),  # acquire retry lock to pass only one retry
            ]
            _, pending = await wait(coros, return_when=FIRST_COMPLETED)
            for coro in pending:
                coro.cancel()
            yield

    async def __call__(self, func: Callable[..., Awaitable[R]]) -> R:
        while True:
            async with self._gate():
                try:
                    result = await func()
                except tuple(self.exceptions):
                    await self._fail()
                else:
                    await self._success()
                    return result

    async def _fail(self):
        async with self._state_lock:
            self._successes = 0
            self._failures += 1
            self._last_failure = max(datetime.now(), self._last_failure)

            self._middle_semaphore._value -= self._middle_semaphore._value  # clear _middle_semaphore

        await self._refresh_state()

    async def _success(self):
        async with self._state_lock:
            self._failures = 0
            self._successes += 1
            self._middle_semaphore.release()  # pass one waiting middle

        await self._refresh_state()

    async def _refresh_state(self) -> CircuitState:
        async with self._state_lock:
            if (
                self._successes > self.recovery_threshold
                or (datetime.now() - self._last_failure) > self.recovery_timeout
            ):
                self._closed_event.set()
                return CircuitState.CLOSED
            self._closed_event.clear()

            if self._failures:
                return CircuitState.OPEN
            return CircuitState.MIDDLE
