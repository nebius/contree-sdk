"""Snapshot decisions and timers owned by execution-notified policies."""

from __future__ import annotations

import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future, InvalidStateError
from contextlib import suppress
from enum import Enum
from math import isfinite
from typing import Protocol


class SnapshotEvent(Enum):
    """Notifications for one policy instance owned by one lazy session.

    RESET starts a new VM cycle. COMMAND_STARTED reserves an accepted command
    before its subprocess is created. COMMAND_FINISHED confirms its exit event,
    including nonzero exits. CLOSE releases resources after completion or failure.
    """

    RESET = "reset"
    COMMAND_STARTED = "command_started"
    COMMAND_FINISHED = "command_finished"
    CLOSE = "close"


class SnapshotTimer(Protocol):
    """Cancellation handle returned by a policy's timer factory."""

    def cancel(self) -> None: ...


TimerFactory = Callable[[float, Callable[[], None]], SnapshotTimer]


def _start_timer(seconds: float, callback: Callable[[], None]) -> SnapshotTimer:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        timer = threading.Timer(seconds, callback)
        timer.daemon = True
        timer.start()
        return timer
    return loop.call_later(seconds, callback)


def _resolve(future: Future[None], error: BaseException | None = None) -> None:
    # A previous cycle can be cancelled while a timer or child policy completes.
    with suppress(InvalidStateError):
        if error is None:
            future.set_result(None)
        else:
            future.set_exception(error)


class AbstractSnapshotPolicy(ABC):
    """Own the decision state and expose one future per VM cycle.

    Use one policy instance per lazy session. Subclasses call super().__init__()
    and super().notify(event) to reset or cancel the cycle future. Resolve the
    future to request a snapshot, or fail it to report a policy error. The session
    still waits for all accepted commands before stopping its VM.
    """

    def __init__(self) -> None:
        self.future: Future[None] = Future()

    @abstractmethod
    def notify(self, event: SnapshotEvent) -> None:
        """Handle an execution event without blocking or performing network I/O."""
        if event is SnapshotEvent.RESET:
            self.future.cancel()
            self.future = Future()
        elif event is SnapshotEvent.CLOSE:
            self.future.cancel()

    def should_snapshot(self) -> Future[None]:
        """Return this cycle's future; successful completion requests a snapshot.

        The caller must not cancel or resolve it. To await it from asyncio, use
        shield(wrap_future(...)) so cancellation does not affect the policy.

        Returns:
            A future shared by all readers of the current policy decision.

        """
        return self.future


class IdleSnapshotPolicy(AbstractSnapshotPolicy):
    """Request a snapshot after all commands have been idle for seconds.

    Timers start on the last command's exit and are cancelled on admission,
    reset, or close. Async callers use their event loop's timer; sync callers
    use a daemon threading.Timer. Inject timer_factory for a custom scheduler.
    """

    def __init__(self, seconds: float, *, timer_factory: TimerFactory = _start_timer) -> None:
        if not isfinite(seconds) or seconds <= 0:
            raise ValueError("idle seconds must be finite and positive")
        super().__init__()
        self.seconds = seconds
        self.timer_factory = timer_factory
        self._lock = threading.RLock()
        self._active = 0
        self._generation = 0
        self._timer: SnapshotTimer | None = None

    def _cancel_timer(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _expired(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation and self._active == 0:
                self._timer = None
                _resolve(self.future)

    def notify(self, event: SnapshotEvent) -> None:
        with self._lock:
            super().notify(event)
            if event in {SnapshotEvent.RESET, SnapshotEvent.CLOSE}:
                self._cancel_timer()
                self._active = 0
            elif event is SnapshotEvent.COMMAND_STARTED:
                self._cancel_timer()
                self._active += 1
            elif event is SnapshotEvent.COMMAND_FINISHED:
                if self._active <= 0:
                    raise ValueError("command finish has no matching admission")
                self._active -= 1
                if self._active == 0 and not self.future.done():
                    generation = self._generation
                    self._timer = self.timer_factory(self.seconds, lambda: self._expired(generation))


class CommandCountSnapshotPolicy(AbstractSnapshotPolicy):
    """Request a snapshot after exactly limit command admissions in one VM."""

    def __init__(self, limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("command limit must be a positive integer")
        super().__init__()
        self.limit = limit
        self.commands_started = 0

    def notify(self, event: SnapshotEvent) -> None:
        super().notify(event)
        if event in {SnapshotEvent.RESET, SnapshotEvent.CLOSE}:
            self.commands_started = 0
        elif event is SnapshotEvent.COMMAND_STARTED:
            self.commands_started += 1
            if self.commands_started >= self.limit:
                _resolve(self.future)


class CompositeSnapshotPolicy(AbstractSnapshotPolicy):
    """Request a snapshot when any child policy's future completes."""

    def __init__(self, *policies: AbstractSnapshotPolicy) -> None:
        if not policies:
            raise ValueError("at least one snapshot policy is required")
        super().__init__()
        self.policies = policies
        self._watch_children()

    def _watch_children(self) -> None:
        target = self.future

        def completed(child: Future[None]) -> None:
            if child.cancelled():
                target.cancel()
            else:
                _resolve(target, child.exception())

        for policy in self.policies:
            policy.should_snapshot().add_done_callback(completed)

    def notify(self, event: SnapshotEvent) -> None:
        super().notify(event)
        for policy in self.policies:
            policy.notify(event)
        if event is SnapshotEvent.RESET:
            self._watch_children()
