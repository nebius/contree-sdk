import asyncio
from asyncio import CancelledError
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

import pytest

from contree_sdk._internals.utils.circuit_retryer import CircuitRetryer, CircuitState


@pytest.fixture
def circuit():
    return CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
    )


async def test_successful_calls_work_normally(circuit):
    async def success_func():
        return "ok"

    result = await circuit(success_func)
    assert result == "ok"


async def test_temporary_failure_retries_and_succeeds():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=1),
        retry_interval=timedelta(seconds=0.01),
    )

    attempts = []

    async def flaky_api():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("temporary error")
        return "recovered"

    result = await circuit(flaky_api)

    assert result == "recovered"
    assert len(attempts) >= 3


async def test_circuit_keeps_retrying_on_persistent_failures():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.1),
        retry_interval=timedelta(seconds=0.01),
    )

    call_count = []

    async def always_fails():
        call_count.append(1)
        raise ValueError("service down")

    task = asyncio.create_task(circuit(always_fails))
    await asyncio.sleep(0.15)
    task.cancel()

    with suppress(CancelledError):
        await task

    assert len(call_count) > 3


async def test_parallel_calls_with_mixed_success_failure():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.1),
        retry_interval=timedelta(seconds=0.01),
    )

    call_index = {"i": 0}
    lock = asyncio.Lock()

    async def mixed_api():
        async with lock:
            idx = call_index["i"]
            call_index["i"] += 1

        await asyncio.sleep(0.01)

        if idx % 3 == 0:
            raise ValueError("occasional failure")
        return f"result_{idx}"

    results = await asyncio.gather(*[circuit(mixed_api) for _ in range(10)])

    assert len(results) == 10
    assert all(isinstance(r, str) for r in results)


async def test_parallel_calls_during_recovery():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
        recovery_threshold=3,
        retry_interval=timedelta(seconds=0.01),
    )

    call_count = {"total": 0}
    lock = asyncio.Lock()

    async def recovering_api():
        async with lock:
            call_count["total"] += 1
            count = call_count["total"]

        if count <= 3:
            raise ValueError("recovering")
        return f"success_{count}"

    tasks = [asyncio.create_task(circuit(recovering_api)) for _ in range(5)]

    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert all("success" in r for r in results)


async def test_open_state_serializes_retries():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        retry_interval=timedelta(seconds=0.02),
    )

    await circuit._fail()

    current = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def always_fails():
        nonlocal current, max_concurrent
        async with lock:
            current += 1
            max_concurrent = max(max_concurrent, current)
        await asyncio.sleep(0.01)
        async with lock:
            current -= 1
        raise ValueError("fail")

    tasks = [asyncio.create_task(circuit(always_fails)) for _ in range(5)]
    await asyncio.sleep(0.2)
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert max_concurrent == 1


async def test_parallel_calls_with_gradual_recovery():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
        recovery_threshold=5,
        retry_interval=timedelta(seconds=0.01),
    )

    success_count = {"count": 0}
    lock = asyncio.Lock()

    async def gradually_recovering_api():
        async with lock:
            success_count["count"] += 1
            count = success_count["count"]

        if count <= 3:
            raise ValueError("still recovering")

        await asyncio.sleep(0.01)
        return f"success_{count}"

    results = await asyncio.gather(*[circuit(gradually_recovering_api) for _ in range(8)])

    assert len(results) == 8
    assert all("success" in r for r in results)


async def test_parallel_calls_handle_different_exception_types():
    circuit = CircuitRetryer(
        exceptions=[ValueError, ConnectionError],
        recovery_timeout=timedelta(seconds=0.1),
        retry_interval=timedelta(seconds=0.01),
    )

    call_index = {"i": 0}
    lock = asyncio.Lock()

    async def multi_exception_api():
        async with lock:
            idx = call_index["i"]
            call_index["i"] += 1

        if idx == 0:
            raise ValueError("first type")
        if idx == 1:
            raise ConnectionError("second type")
        if idx == 2:
            raise RuntimeError("non-retriable")
        return f"success_{idx}"

    results = []
    exceptions = []

    for _ in range(4):
        try:
            result = await circuit(multi_exception_api)
            results.append(result)
        except RuntimeError as e:
            exceptions.append(e)

    assert len(results) >= 1
    assert len(exceptions) == 1


async def test_external_context_manager_wraps_calls():
    events = []

    @asynccontextmanager
    async def tracking_middleware():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    circuit = CircuitRetryer(exceptions=[ValueError], external_contexts=[tracking_middleware()])

    async def api_call():
        events.append("call")
        return "done"

    result = await circuit(api_call)

    assert result == "done"
    assert events == ["enter", "call", "exit"]


async def test_non_retriable_exceptions_propagate_immediately(circuit):
    async def wrong_exception_func():
        raise RuntimeError("not a ValueError")

    with pytest.raises(RuntimeError):
        await circuit(wrong_exception_func)


async def test_multiple_failures_then_success():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
        retry_interval=timedelta(seconds=0.01),
    )

    results = []
    fail_count = 0

    async def intermittent_api():
        nonlocal fail_count
        fail_count += 1
        if fail_count % 3 == 0:
            return f"success_{fail_count}"
        raise ValueError("intermittent")

    for _ in range(3):
        result = await circuit(intermittent_api)
        results.append(result)

    assert len(results) == 3
    assert all("success" in r for r in results)


async def test_no_deadlock_all_waiters_get_through():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
        retry_interval=timedelta(seconds=0.01),
    )

    completed = []

    async def api_call(idx):
        result = await circuit(lambda: asyncio.sleep(0))
        completed.append(idx)
        return result

    await asyncio.wait_for(asyncio.gather(*[api_call(i) for i in range(20)]), timeout=1.0)

    assert len(completed) == 20


async def test_no_deadlock_retry_lock_released_on_success():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.1),
        retry_interval=timedelta(seconds=0.02),
    )

    call_count = 0

    async def flaky_then_success():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("first fails")
        return "ok"

    result1 = await circuit(flaky_then_success)
    assert result1 == "ok"

    call_count = 0
    result2 = await circuit(flaky_then_success)
    assert result2 == "ok"


async def test_no_deadlock_high_contention_on_state_lock():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
    )

    async def rapid_state_change(idx):
        if idx % 2 == 0:
            await circuit._fail()
        else:
            await circuit._success()
        return await circuit._refresh_state()

    results = await asyncio.wait_for(asyncio.gather(*[rapid_state_change(i) for i in range(50)]), timeout=1.0)

    assert len(results) == 50


async def test_race_gate_cancel_during_entry():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
    )

    async def call_with_cancel():
        async with circuit._gate():
            await asyncio.sleep(0.1)
        return "done"

    task = asyncio.create_task(call_with_cancel())
    await asyncio.sleep(0.02)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    result = await asyncio.wait_for(circuit(lambda: asyncio.sleep(0)), timeout=0.5)
    assert result is None


async def test_no_deadlock_external_context_blocks():
    slow_sem = asyncio.Semaphore(1)
    circuit = CircuitRetryer(exceptions=[ValueError], external_contexts=[slow_sem])

    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def slow_call(idx):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1
        return idx

    async def make_call(idx):
        return await circuit(lambda: slow_call(idx))

    results = await asyncio.wait_for(asyncio.gather(*[make_call(i) for i in range(5)]), timeout=1.0)

    assert len(results) == 5
    assert max_active <= 1


async def test_parallel_calls_respect_external_semaphore():
    rate_limiter = asyncio.Semaphore(3)
    circuit = CircuitRetryer(exceptions=[ValueError], external_contexts=[rate_limiter])

    active = {"count": 0, "max": 0}
    lock = asyncio.Lock()

    async def rate_limited_api(idx):
        async with lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])

        await asyncio.sleep(0.05)

        async with lock:
            active["count"] -= 1

        return f"result_{idx}"

    async def make_call(idx):
        return await circuit(lambda: rate_limited_api(idx))

    results = await asyncio.gather(*[make_call(i) for i in range(15)])

    assert len(results) == 15
    assert active["max"] <= 3


async def test_recovery_threshold_exact_boundary():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        recovery_threshold=3,
    )

    await circuit._fail()

    for _ in range(3):
        await circuit._success()
    assert await circuit._refresh_state() != CircuitState.CLOSED

    await circuit._success()
    assert await circuit._refresh_state() == CircuitState.CLOSED


async def test_recovery_via_timeout_not_retry_lock():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=0.05),
        retry_interval=timedelta(seconds=10),
    )

    await circuit._fail()
    assert await circuit._refresh_state() == CircuitState.OPEN

    result = await asyncio.wait_for(circuit(lambda: asyncio.sleep(0)), timeout=0.5)
    assert result is None
    assert await circuit._refresh_state() == CircuitState.CLOSED


async def test_healthy_circuit_opens_on_failures():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        retry_interval=timedelta(seconds=0.05),
    )

    assert await circuit._refresh_state() == CircuitState.CLOSED

    await circuit._fail()
    assert await circuit._refresh_state() == CircuitState.OPEN

    call_times = []

    async def always_fails():
        call_times.append(asyncio.get_event_loop().time())
        raise ValueError("still down")

    task = asyncio.create_task(circuit(always_fails))
    await asyncio.sleep(0.18)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    gaps = [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]
    assert all(g >= 0.04 for g in gaps)


async def test_retry_max_amount_raises_after_limit():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        retry_interval=timedelta(seconds=0),
        retry_max_amount=2,
    )
    calls = 0

    async def always_fails():
        nonlocal calls
        calls += 1
        raise ValueError("fail")

    with pytest.raises(ValueError):
        await circuit(always_fails)

    assert calls == 3


async def test_retry_timeout_raises_after_deadline():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        retry_interval=timedelta(seconds=0.01),
        retry_timeout=timedelta(seconds=0.05),
    )

    async def always_fails():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        await circuit(always_fails)


async def test_max_failures_cuts_off_all_parallel_callers():
    circuit = CircuitRetryer(
        exceptions=[ValueError],
        recovery_timeout=timedelta(seconds=10),
        retry_interval=timedelta(seconds=0),
        retry_max_amount=100,
        max_failures=3,
    )

    async def always_fails():
        raise ValueError("parallel fail")

    results = await asyncio.gather(*[circuit(always_fails) for _ in range(5)], return_exceptions=True)

    assert all(isinstance(r, ValueError) for r in results)


async def test_many_parallel_calls_under_load(circuit):
    processed = []
    lock = asyncio.Lock()

    async def api_under_load(idx):
        await asyncio.sleep(0.01)
        async with lock:
            processed.append(idx)
        return idx

    async def make_call(idx):
        return await circuit(lambda: api_under_load(idx))

    results = await asyncio.gather(*[make_call(i) for i in range(50)])

    assert len(results) == 50
    assert sorted(results) == list(range(50))
