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
from contree_sdk.session.snapshot_policy import DurationSnapshotPolicy
from tests.unit.session.timers import ManualTimers


START = SnapshotEvent.COMMAND_STARTED
FINISH = SnapshotEvent.COMMAND_FINISHED
RESET = SnapshotEvent.RESET
CLOSE = SnapshotEvent.CLOSE


def test_duration_expires_during_activity_without_restarting():
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start)
    policy.notify(RESET)
    future = policy.should_snapshot()
    assert not timers.timers
    policy.notify(SnapshotEvent.VM_STARTING)
    timers.advance(3)
    policy.notify(SnapshotEvent.VM_STARTING)
    policy.notify(START)
    timers.advance(3)
    policy.notify(FINISH)
    policy.notify(SnapshotEvent.INSPECTION_STARTED)
    timers.advance(3)
    assert not future.done()
    timers.advance(1)
    assert future.result(timeout=0) is None
    assert len(timers.timers) == 1
    policy.notify(SnapshotEvent.INSPECTION_FINISHED)
    assert policy.should_snapshot() is future


def test_duration_reset_and_close_cancel_timers_and_ignore_stale_callbacks():
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start)
    policy.notify(SnapshotEvent.VM_STARTING)
    first = policy.should_snapshot()
    old_timer = timers.timers[-1]
    policy.notify(RESET)
    assert first.cancelled()
    assert old_timer.cancelled
    assert policy.timer is None
    policy.notify(SnapshotEvent.VM_STARTING)
    second = policy.should_snapshot()
    old_timer.callback()
    assert not second.done()
    policy.notify(CLOSE)
    assert second.cancelled()
    assert timers.timers[-1].cancelled
    assert policy.timer is None
    timers.timers[-1].callback()
    policy.notify(SnapshotEvent.VM_STARTING)
    assert len(timers.timers) == 2


async def test_async_duration_uses_loop_timer_and_releases_it_on_close():
    policy = DurationSnapshotPolicy(60)
    policy.notify(SnapshotEvent.VM_STARTING)
    timer = policy.timer
    assert isinstance(timer, asyncio.TimerHandle)
    policy.notify(CLOSE)
    assert timer.cancelled()
    assert policy.timer is None
    assert policy.should_snapshot().cancelled()


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_duration_interval(value):
    with pytest.raises(ValueError, match="finite and positive"):
        DurationSnapshotPolicy(value)


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


def test_duration_updates_deadline_without_losing_elapsed_startup_time():
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start, clock=lambda: timers.now)
    policy.notify(SnapshotEvent.VM_STARTING)
    original = timers.timers[-1]
    timers.advance(3)
    policy.set_duration(20)
    assert original.cancelled
    assert timers.timers[-1].deadline == 20
    original.callback()
    assert not policy.should_snapshot().done()
    timers.advance(10)
    policy.set_duration(12)
    assert policy.should_snapshot().result(timeout=0) is None
    assert policy.timer is None


def test_deferred_duration_uses_effective_deadline_and_original_start_time():
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start, clock=lambda: timers.now)
    policy.start_deferred()
    policy.notify(SnapshotEvent.VM_STARTING)
    timers.advance(15)
    assert not timers.timers
    assert not policy.should_snapshot().done()
    policy.set_duration(20)
    assert timers.timers[-1].deadline == 20
    timers.advance(5)
    assert policy.should_snapshot().result(timeout=0) is None
    policy.notify(CLOSE)


def test_duration_configuration_before_start_and_reset_uses_new_start_time():
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start, clock=lambda: timers.now)
    policy.set_duration(5)
    assert not timers.timers
    timers.advance(7)
    policy.notify(SnapshotEvent.VM_STARTING)
    assert timers.timers[-1].deadline == 12
    policy.notify(RESET)
    assert policy.started_at is None
    timers.advance(3)
    policy.notify(SnapshotEvent.VM_STARTING)
    assert timers.timers[-1].deadline == 15
    policy.notify(CLOSE)
    assert all(timer.cancelled for timer in timers.timers)


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_invalid_duration_update_preserves_current_timer(seconds):
    timers = ManualTimers()
    policy = DurationSnapshotPolicy(10, timer_factory=timers.start)
    policy.notify(SnapshotEvent.VM_STARTING)
    original = policy.timer
    with pytest.raises(ValueError, match="finite and positive"):
        policy.set_duration(seconds)
    assert policy.timer is original
    assert not timers.timers[-1].cancelled
    policy.notify(CLOSE)
