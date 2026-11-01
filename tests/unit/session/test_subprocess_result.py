from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from contree_client.models import (
    EventDataExit,
    EventDataSpawn,
    EventDataStream,
    EventDataTruncated,
    EventResources,
    InstanceResultResources,
    InstanceResultState,
    OperationEvent,
    StreamRepr,
)

from contree_sdk.session.subprocess_result import SubprocessResult


def event(kind, data=None):
    return OperationEvent(id=1, ts=datetime.now(timezone.utc), type=kind, spid=2, data=data or {})


def spawn(limit=0):
    return event(
        "spawn",
        EventDataSpawn(
            pid=123, command="echo", args=[], shell=False, cwd="/", uid=0, gid=0, timeout=60, truncate_at=limit
        ),
    )


def exited(**kwargs):
    return event(
        "exit",
        EventDataExit(
            pid=123,
            code=kwargs.pop("code", 0),
            signal=kwargs.pop("signal", -1),
            timed_out=kwargs.pop("timed_out", False),
            duration_ms=1234,
            resources=EventResources(
                user_time_us=125000,
                sys_time_us=250000,
                max_rss_kb=1024,
                shared_memory=1,
                unshared_memory=2,
                swaps=3,
                minor_faults=4,
                major_faults=5,
                voluntary_ctx_switches=6,
                involuntary_ctx_switches=7,
                block_input_ops=8,
                block_output_ops=9,
                ipc_msgs_sent=10,
                ipc_msgs_received=11,
                signals_received=12,
            ),
            **kwargs,
        ),
    )


def test_binary_chunks_remain_exact_and_streams_are_independent():
    accumulator = SubprocessResult()
    accumulator.observe(spawn())
    for stream, content in [("stdout", b"hello\n"), ("stderr", b"\xff\x00"), ("stdout", b"\x80world")]:
        accumulator.observe(event(stream, EventDataStream.from_bytes(content)))
    accumulator.observe(exited())

    result = accumulator.result()

    assert result.stdout == StreamRepr(value="aGVsbG8KgHdvcmxk", encoding="base64", truncated=False)
    assert result.stderr == StreamRepr(value="/wA=", encoding="base64", truncated=False)
    assert accumulator.result() == result


def test_empty_output_and_complete_resources_state_mapping():
    accumulator = SubprocessResult()
    accumulator.observe(spawn())
    accumulator.observe(exited())

    result = accumulator.result()

    assert result.stdout == StreamRepr(value="", encoding="ascii", truncated=False)
    assert result.stderr == StreamRepr(value="", encoding="ascii", truncated=False)
    assert result.state == InstanceResultState(
        pid=123,
        exit_code=0,
        signal=-1,
        timed_out=False,
        core_dump=False,
        oom_killed=False,
        continued=False,
        stopped=False,
    )
    assert result.resources == InstanceResultResources(
        block_input=8,
        block_output=9,
        elapsed_time=0.375,
        involuntary_switches=7,
        max_rss=1024,
        monotonic_time=1.234,
        page_faults=5,
        page_faults_io=4,
        shared_memory=1,
        signals=12,
        swaps=3,
        system_cpu_time=0.25,
        unshared_memory=2,
        user_cpu_time=0.125,
        voluntary_switches=6,
    )
    assert isinstance(result.resources, InstanceResultResources)
    assert result.resources.cost is Ellipsis


@pytest.mark.parametrize(("code", "signal"), [(7, -1), (-1, 9)])
def test_nonzero_exit_and_signal_preserve_state_flags(code, signal):
    accumulator = SubprocessResult()
    accumulator.observe(spawn())
    accumulator.observe(exited(code=code, signal=signal, timed_out=True, core_dump=True, oom_killed=True))

    assert accumulator.result().state == InstanceResultState(
        pid=123,
        exit_code=code,
        signal=signal,
        timed_out=True,
        core_dump=True,
        oom_killed=True,
        continued=False,
        stopped=False,
    )


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_stream_cap_bounds_output_across_chunks(stream):
    accumulator = SubprocessResult()
    accumulator.observe(spawn(limit=3))
    accumulator.observe(event(stream, EventDataStream.from_bytes(b"ab")))
    accumulator.observe(event(stream, EventDataStream.from_bytes(b"cdef")))
    accumulator.observe(event(stream, EventDataStream.from_bytes(b"ghi")))
    accumulator.observe(exited())

    result = accumulator.result()

    assert getattr(result, stream) == StreamRepr(value="abc", encoding="ascii", truncated=True)
    assert len(getattr(accumulator, stream)) == 3


def test_exact_cap_is_not_truncated_without_summary():
    accumulator = SubprocessResult()
    accumulator.observe(spawn(limit=3))
    accumulator.observe(event("stdout", EventDataStream.from_bytes(b"abc")))
    accumulator.observe(exited())

    assert accumulator.result().stdout == StreamRepr(value="abc", encoding="ascii", truncated=False)


@pytest.mark.parametrize("stream", ["stdout", "stderr", "stdin"])
def test_truncation_summary_marks_only_affected_output(stream):
    accumulator = SubprocessResult()
    accumulator.observe(spawn(limit=3))
    accumulator.observe(event("stdout", EventDataStream.from_bytes(b"abc")))
    accumulator.observe(event("truncated", EventDataTruncated(stream=stream, bytes_emitted=3, bytes_dropped=10)))
    accumulator.observe(exited())

    result = accumulator.result()

    assert isinstance(result.stdout, StreamRepr)
    assert isinstance(result.stderr, StreamRepr)
    assert result.stdout.truncated is (stream == "stdout")
    assert result.stderr.truncated is (stream == "stderr")


def test_global_size_cap_before_spawn_preserves_incomplete_output():
    accumulator = SubprocessResult()
    accumulator.observe(event("size_cap"))
    accumulator.observe(spawn())
    accumulator.observe(exited())

    result = accumulator.result()
    assert isinstance(result.stdout, StreamRepr)
    assert isinstance(result.stderr, StreamRepr)
    assert result.stdout.truncated is True
    assert result.stderr.truncated is True


@pytest.mark.parametrize("events", [[], [spawn()], [exited()]])
def test_missing_lifecycle_events_cannot_produce_a_result(events):
    accumulator = SubprocessResult()
    for item in events:
        accumulator.observe(item)

    with pytest.raises(RuntimeError, match="incomplete"):
        accumulator.result()


@pytest.mark.parametrize(
    "data",
    [
        EventDataStream(value="!not-base64!", encoding="base64"),
        EventDataStream(value="YQ", encoding="base64"),
        EventDataStream(value="é", encoding="ascii"),
        EventDataStream.from_dict({"value": "abc", "encoding": "unknown"}),
        {},
    ],
)
def test_invalid_output_is_not_silently_discarded(data):
    accumulator = SubprocessResult()
    accumulator.observe(spawn())

    with pytest.raises(RuntimeError, match="invalid subprocess stdout event") as failure:
        accumulator.observe(event("stdout", data))
    with pytest.raises(RuntimeError) as repeated:
        accumulator.result()
    assert repeated.value is failure.value
    with pytest.raises(RuntimeError) as next_event:
        accumulator.observe(exited())
    assert next_event.value is failure.value


@pytest.mark.parametrize("kind", ["spawn", "exit", "truncated"])
def test_malformed_lifecycle_payloads_raise(kind):
    accumulator = SubprocessResult()

    with pytest.raises(RuntimeError, match="invalid subprocess"):
        accumulator.observe(event(kind))


def test_output_without_spawn_raises():
    accumulator = SubprocessResult()

    with pytest.raises(RuntimeError, match="without a spawn"):
        accumulator.observe(event("stdout", EventDataStream.from_bytes(b"data")))


@pytest.mark.parametrize("item", [spawn(), exited()])
def test_duplicate_lifecycle_events_raise(item):
    accumulator = SubprocessResult()
    accumulator.observe(item)

    with pytest.raises(RuntimeError, match="expected one"):
        accumulator.observe(item)


@pytest.mark.parametrize("limit", [0.0, 3.0, 1048576.0])
def test_integer_valued_json_floats_produce_integer_state_and_resources(limit):
    spawn_payload = spawn().data
    exit_payload = exited().data
    assert isinstance(spawn_payload, EventDataSpawn)
    assert isinstance(exit_payload, EventDataExit)
    spawn_data = EventDataSpawn.from_dict({**spawn_payload.to_dict(), "pid": 123.0, "truncate_at": limit})
    exit_data = EventDataExit.from_dict({
        **exit_payload.to_dict(),
        "pid": 123.0,
        "code": 0.0,
        "signal": -1.0,
        "duration_ms": 1234.0,
        "resources": {name: float(value) for name, value in asdict(exit_payload.resources).items()},
    })
    accumulator = SubprocessResult()
    accumulator.observe(event("spawn", spawn_data))
    accumulator.observe(event("stdout", EventDataStream.from_bytes(b"hello")))
    accumulator.observe(event("exit", exit_data))

    result = accumulator.result()

    assert result.stdout == StreamRepr(value="hel" if limit == 3 else "hello", encoding="ascii", truncated=limit == 3)
    assert isinstance(result.state, InstanceResultState)
    assert isinstance(result.resources, InstanceResultResources)
    assert type(result.state.pid) is int
    assert type(result.state.exit_code) is int
    assert type(result.state.signal) is int
    float_fields = {"cost", "elapsed_time", "monotonic_time", "system_cpu_time", "user_cpu_time"}
    for name, value in asdict(result.resources).items():
        if name not in float_fields:
            assert type(value) is int
    assert result.resources.max_rss == 1024
    assert result.resources.monotonic_time == pytest.approx(1.234)
    assert result.resources.user_cpu_time == pytest.approx(0.125)
    assert result.resources.cost is Ellipsis


@pytest.mark.parametrize("limit", [1.5, float("nan"), float("inf"), float("-inf"), True, "3", None])
def test_invalid_output_limit_is_rejected_without_truncating_it(limit):
    spawn_payload = spawn().data
    assert isinstance(spawn_payload, EventDataSpawn)
    payload = EventDataSpawn.from_dict({**spawn_payload.to_dict(), "truncate_at": limit})
    accumulator = SubprocessResult()

    with pytest.raises(RuntimeError, match="integer-valued") as failure:
        accumulator.observe(event("spawn", payload))
    with pytest.raises(RuntimeError) as repeated:
        accumulator.result()
    assert repeated.value is failure.value


def test_nonintegral_resource_counter_is_rejected():
    payload = exited().data
    assert isinstance(payload, EventDataExit)
    data = asdict(payload)
    data["resources"]["max_rss_kb"] = 1.5
    accumulator = SubprocessResult()
    accumulator.observe(spawn())

    with pytest.raises(RuntimeError, match="integer-valued"):
        accumulator.observe(event("exit", EventDataExit.from_dict(data)))
