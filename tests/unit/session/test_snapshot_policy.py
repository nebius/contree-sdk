import asyncio
from concurrent.futures import Future

import pytest

from contree_sdk.session import (
    AbstractSnapshotPolicy,
    CommandCountSnapshotPolicy,
    CompositeSnapshotPolicy,
    IdleSnapshotPolicy,
    SnapshotEvent,
)
from tests.unit.session.timers import ManualTimers


START = SnapshotEvent.COMMAND_STARTED
FINISH = SnapshotEvent.COMMAND_FINISHED
RESET = SnapshotEvent.RESET
CLOSE = SnapshotEvent.CLOSE


def test_idle_future_counts_only_idle_time_and_ignores_stale_timers():
    timers = ManualTimers()
    policy = IdleSnapshotPolicy(3, timer_factory=timers.start)
    policy.notify(RESET)
    future = policy.should_snapshot()
    assert isinstance(future, Future)
    assert not timers.timers
    policy.notify(START)
    timers.advance(100)
    assert not future.done()
    policy.notify(FINISH)
    old_timer = timers.timers[-1]
    timers.advance(2.999)
    assert not future.done()
    policy.notify(START)
    assert old_timer.cancelled
    old_timer.callback()  # A callback already queued when admission cancelled its timer.
    assert not future.done()
    policy.notify(FINISH)
    timers.advance(3)
    assert future.result(timeout=0) is None
    assert policy.should_snapshot() is future


def test_idle_waits_for_all_commands_and_cancels_timer_on_reset_and_close():
    timers = ManualTimers()
    policy = IdleSnapshotPolicy(5, timer_factory=timers.start)
    policy.notify(START)
    policy.notify(START)
    policy.notify(FINISH)
    assert not timers.timers
    policy.notify(FINISH)
    first = policy.should_snapshot()
    policy.notify(RESET)
    assert first.cancelled()
    assert timers.timers[-1].cancelled
    policy.notify(START)
    policy.notify(FINISH)
    second = policy.should_snapshot()
    policy.notify(CLOSE)
    timers.advance(10)
    assert second.cancelled()
    assert all(timer.cancelled for timer in timers.timers)


def test_count_resolves_at_admission_and_resets_each_cycle():
    policy = CommandCountSnapshotPolicy(2)
    first = policy.should_snapshot()
    policy.notify(START)
    assert not first.done()
    policy.notify(START)
    assert first.result(timeout=0) is None
    policy.notify(FINISH)
    policy.notify(FINISH)
    policy.notify(RESET)
    assert not policy.should_snapshot().done()
    assert policy.commands_started == 0
    policy.notify(START)
    assert not policy.should_snapshot().done()
    policy.notify(CLOSE)
    assert policy.should_snapshot().cancelled()


def test_composite_propagates_idle_count_and_custom_failure():
    class Custom(AbstractSnapshotPolicy):
        def notify(self, event):
            super().notify(event)

    timers = ManualTimers()
    idle = IdleSnapshotPolicy(5, timer_factory=timers.start)
    custom = Custom()
    policy = CompositeSnapshotPolicy(idle, CommandCountSnapshotPolicy(3), custom)
    first = policy.should_snapshot()
    policy.notify(START)
    policy.notify(FINISH)
    timers.advance(5)
    assert first.result(timeout=0) is None
    policy.notify(RESET)
    for _ in range(3):
        policy.notify(START)
    assert policy.should_snapshot().result(timeout=0) is None
    policy.notify(RESET)
    custom.future.set_exception(ValueError("custom policy failed"))
    with pytest.raises(ValueError, match="custom policy failed"):
        policy.should_snapshot().result(timeout=0)
    policy.notify(RESET)
    custom.future.cancel()
    assert policy.should_snapshot().cancelled()
    policy.notify(CLOSE)
    assert idle.should_snapshot().cancelled()


async def test_async_idle_uses_loop_timer_and_shielded_wait_keeps_policy_future():
    policy = IdleSnapshotPolicy(0.01)
    policy.notify(START)
    policy.notify(FINISH)
    assert isinstance(policy._timer, asyncio.TimerHandle)
    future = policy.should_snapshot()
    waiting = asyncio.shield(asyncio.wrap_future(future))
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert not future.cancelled()
    await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), 1)
    assert future.done()
    policy.notify(CLOSE)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_idle_interval(value):
    with pytest.raises(ValueError):
        IdleSnapshotPolicy(value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_count(value):
    with pytest.raises(ValueError):
        CommandCountSnapshotPolicy(value)


def test_empty_composite_and_abstract_policy_are_rejected():
    with pytest.raises(ValueError):
        CompositeSnapshotPolicy()
    with pytest.raises(TypeError):
        AbstractSnapshotPolicy()


def test_sync_idle_timer_is_released_on_close():
    import threading

    policy = IdleSnapshotPolicy(60)
    policy.notify(START)
    policy.notify(FINISH)
    timer = policy._timer
    assert isinstance(timer, threading.Timer)
    policy.notify(CLOSE)
    timer.join(timeout=1)
    assert not timer.is_alive()
    assert policy.should_snapshot().cancelled()
