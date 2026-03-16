import logging
from asyncio import FIRST_COMPLETED, Event, Lock, Semaphore, create_task, sleep, wait
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta
from enum import auto
from typing import TypeVar

from strenum import StrEnum

from contree_sdk._internals.utils.other import get_interval


R = TypeVar("R")

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    OPEN = auto()
    CLOSED = auto()
    MIDDLE = auto()


class CircuitRetrier:
    """Async circuit breaker with built-in retry logic.

    Wraps async callables and retries them on configured exceptions while
    managing three circuit states:
    - CLOSED: circuit is healthy, requests pass through freely.
    - OPEN: failures detected; only one retry is allowed at a time via a
      serializing lock with a mandatory interval between attempts.
    - MIDDLE: partial recovery; each success releases one additional slot,
      allowing traffic to ramp up gradually before the circuit fully closes.

    Hard limits (retry_max_amount, retry_timeout, max_failures) cause the
    exception to propagate instead of being retried once any limit is exceeded.

    Args:
        exceptions: Exception types that trigger a retry. Defaults to all exceptions.
        recovery_timeout: Time since the last failure after which the circuit
            recovers automatically regardless of success count.
        recovery_threshold: Number of consecutive successes to exceed to close
            the circuit from MIDDLE state.
        external_contexts: Async context managers or zero-argument callables returning
            async context managers, entered on every call before the circuit gate.
            Instances (e.g. semaphores) are reused as-is; callables are invoked
            on each call to produce a fresh context manager.
        retry_interval_min: Minimum pause between consecutive retries in OPEN state
            (used when failures are low).
        retry_interval_max: Maximum pause between retries, reached when failures
            approach max_failures. Interval grows logarithmically between min and max.
        retry_timeout: Maximum total time a single __call__ invocation may spend
            retrying before the exception is re-raised.
        retry_max_amount: Maximum number of retry attempts per __call__ invocation.
        max_failures: Maximum cumulative circuit-wide failure count before the
            exception is re-raised across all concurrent callers.

    """

    def __init__(
        self,
        exceptions: Sequence[type[Exception]] | None = None,
        recovery_timeout: timedelta = timedelta(seconds=20),
        recovery_threshold: int = 10,
        external_contexts: list[AbstractAsyncContextManager | Callable[[], AbstractAsyncContextManager]] | None = None,
        retry_interval_min: timedelta = timedelta(seconds=1),
        retry_interval_max: timedelta = timedelta(seconds=30),
        retry_timeout: timedelta = timedelta(minutes=60),
        retry_max_amount: int = 100,
        max_failures: int = 1000,
    ):
        self.exceptions = exceptions or [Exception]
        self.external_contexts = external_contexts or []

        # state
        self._state_lock = Lock()
        self._failures = 0
        self._successes = 0
        self._last_failure: datetime = datetime.min
        self.max_failures = max_failures

        # middle
        self._middle_semaphore = Semaphore()
        self.recovery_threshold = recovery_threshold
        self.recovery_timeout = recovery_timeout

        # closed
        self._closed_event = Event()  # set, when fully closed
        self._closed_event.set()

        # retries
        self._retry_lock = Lock()
        self.retry_interval_min = retry_interval_min
        self.retry_interval_max = retry_interval_max
        self.retry_max_amount = retry_max_amount
        self.retry_timeout = retry_timeout

    async def _wait_recovery(self):
        while True:
            state = await self._refresh_state()
            if state == CircuitState.CLOSED:
                return
            await sleep(max((self.recovery_timeout - (datetime.now() - self._last_failure)).total_seconds(), 0))

    @asynccontextmanager
    async def _with_retry_lock(self):
        async with self._retry_lock:
            failures_ratio = min(self._failures / self.max_failures, 1.0) if self.max_failures else 0.0
            interval = get_interval(
                self.retry_interval_min.total_seconds(),
                self.retry_interval_max.total_seconds(),
                failures_ratio,
            )
            interval = min(interval, self.retry_timeout.total_seconds())
            await sleep(interval)
            yield

    @asynccontextmanager
    async def _gate(self):
        """Block until a request is allowed to proceed based on circuit state.

        Waits for the first of: circuit CLOSED, recovery timeout elapsed,
        MIDDLE-state semaphore slot available, or serializing retry lock
        acquired (OPEN state, one at a time with logarithmically growing delay).
        External contexts are entered before the wait and released on exit.

        """
        async with AsyncExitStack() as exit_stack:
            for ctx in self.external_contexts:
                cm = ctx if isinstance(ctx, AbstractAsyncContextManager) else ctx()
                await exit_stack.enter_async_context(cm)
            coros = [
                create_task(self._closed_event.wait()),  # if circuit is fully closed
                create_task(self._wait_recovery()),  # if circuit is recovered by time
                create_task(self._middle_semaphore.acquire()),  # if circuit is in middle state, wait for more succeeds
                create_task(  # acquire retry lock to pass only one retry
                    exit_stack.enter_async_context(self._with_retry_lock())
                ),
            ]
            _, pending = await wait(coros, return_when=FIRST_COMPLETED)
            for coro in pending:
                coro.cancel()
            yield

    async def __call__(self, func: Callable[..., Awaitable[R]]) -> R:
        """Call func, retrying on configured exceptions until it succeeds or a hard limit is hit.

        Each attempt waits on _gate() to respect the current circuit state.
        On a configured exception the circuit is notified and the call is
        retried, unless retry_max_amount attempts have been made, retry_timeout
        has elapsed, or the circuit-wide max_failures count is reached — in
        which case the exception propagates.

        Args:
            func: Zero-argument async callable to invoke.

        Returns:
            The value returned by func on a successful call.

        """
        number = 0
        started = datetime.now()
        while True:
            async with self._gate():
                try:
                    result = await func()
                except tuple(self.exceptions):
                    await self._fail()
                    if (
                        number >= self.retry_max_amount
                        or (datetime.now() - started) >= self.retry_timeout
                        or self._failures >= self.max_failures
                    ):
                        raise
                    number += 1
                else:
                    await self._success()
                    return result

    async def _fail(self):
        async with self._state_lock:
            self._successes = 0
            self._failures += 1
            self._last_failure = max(datetime.now(), self._last_failure)

            self._middle_semaphore._value = 0  # clear _middle_semaphore

        await self._refresh_state()

    async def _success(self):
        async with self._state_lock:
            self._failures = 0
            self._successes += 1
            # allow 2 more requests to execute
            self._middle_semaphore.release()
            self._middle_semaphore.release()

        await self._refresh_state()

    async def _refresh_state(self) -> CircuitState:
        """Recompute and return the current circuit state.

        Returns CLOSED and sets the closed event when successes exceed
        recovery_threshold or the recovery timeout has elapsed. Otherwise,
        clears the event and returns OPEN if there are active failures,
        or MIDDLE if the failure counter has been reset by a recent success.

        Returns:
            The new CircuitState.

        """
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
