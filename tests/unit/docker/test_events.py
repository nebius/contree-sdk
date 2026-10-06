"""Build notifications use real sessions, stores, and operation event readers."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from contree_client.models import EventDataStream, FileResponse, OperationStatus
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.exceptions import DockerBuildError, FailedOperationError
from contree_sdk.session.base import exit_code_of
from tests.unit.session.factories import operation_response, spawn_response
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def build_case(request, tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nRUN echo hello\n")
    client = ContreeAsyncClient() if request.param else ContreeClient()
    client.mock("resolve_image", "base-image")
    client.mock("cancel_operation", None)
    builder = (
        ContreeAsyncDockerBuilder(client) if isinstance(client, ContreeAsyncClient) else ContreeDockerBuilder(client)
    )
    return client, builder


async def build(builder, path, **kwargs):
    if isinstance(builder, ContreeAsyncDockerBuilder):
        return await builder.build(path, **kwargs)
    return await asyncio.to_thread(builder.build, path, **kwargs)


def output(kind, value):
    return replace(event(kind), data=EventDataStream.from_bytes(value))


def queue_run(client, *, uuid="op-1", image="built-image", **kwargs):
    client.mock("spawn_instance", spawn_response(uuid))
    client.mock("get_operation_status", operation_response(operation_uuid=uuid, result_image_uuid=image, **kwargs))
    client.mock(
        "follow_operation_events", [output("stdout", b"out\x00\xff"), output("stderr", b"err"), event("completion")]
    )


async def test_events_include_binary_output_and_typed_result(build_case, tmp_path):
    client, builder = build_case
    queue_run(client)
    events = []
    assert await build(builder, tmp_path, on_event=events.append) == "built-image"
    assert [item.type for item in events] == [
        "step_started",
        "step_completed",
        "step_started",
        "operation_started",
        "stdout",
        "stderr",
        "step_completed",
    ]
    assert [(item.step.id, item.step.index) for item in events if item.type == "step_started"] == [(0, 0), (1, 1)]
    assert all(item.step.parent_id is None for item in events)
    assert [item.data for item in events if item.type in {"stdout", "stderr"}] == [b"out\x00\xff", b"err"]
    assert all(item.operation_uuid == "op-1" for item in events[3:])
    assert events[-1].image_before == "base-image"
    assert events[-1].image_after == "built-image"
    assert events[-1].result is not None
    assert exit_code_of(events[-1].result) == 0
    assert len(client.calls_for("follow_operation_events")) == 1
    assert len(client.calls_for("get_operation_status")) == 1
    assert not client.calls_for("wait_operation")


async def test_cached_build_has_cache_events_without_output_or_spawn(build_case, tmp_path):
    client, builder = build_case
    queue_run(client)
    await build(builder, tmp_path, session_id="cache")
    events = []
    assert await build(builder, tmp_path, session_id="cache", on_event=events.append) == "built-image"
    assert [item.type for item in events] == [
        "step_started",
        "cache_hit",
        "step_completed",
        "step_started",
        "cache_hit",
        "step_completed",
    ]
    assert all(item.operation_uuid is None for item in events)
    assert len(client.calls_for("spawn_instance")) == 1


@pytest.mark.parametrize(
    ("status", "exit_code", "error_type"),
    [
        (OperationStatus.SUCCESS, 7, DockerBuildError),
        (OperationStatus.FAILED, 0, FailedOperationError),
        (OperationStatus.CANCELLED, 0, InterruptedError),
    ],
)
async def test_failure_preserves_primary_exception_and_does_not_tag(
    build_case, tmp_path, status, exit_code, error_type
):
    client, builder = build_case
    queue_run(client, status=status, exit_code=exit_code, stderr="failed command")
    events = []

    def receive(item):
        events.append(item)
        if item.type == "step_failed":
            raise ValueError("notification failed")

    def summary(item):
        if item.error is not None:
            raise RuntimeError("summary failed")

    with pytest.raises(error_type) as caught:
        await build(builder, tmp_path, tag="result", on_event=receive, on_step=summary)
    assert events[-1].type == "step_failed"
    assert events[-1].error is caught.value
    assert events[-1].operation_uuid == "op-1"
    assert not client.calls_for("update_image_tag")
    if status == OperationStatus.SUCCESS:
        assert events[-1].result is not None
        assert exit_code_of(events[-1].result) == 7


@pytest.mark.parametrize("failure_event", ["operation_started", "stdout"])
async def test_callback_error_cancels_current_operation(build_case, tmp_path, failure_event):
    client, builder = build_case
    queue_run(client)
    error = BrokenPipeError("output closed")
    events = []

    def receive(item):
        events.append(item)
        if item.type == failure_event:
            raise error

    with pytest.raises(BrokenPipeError) as caught:
        await build(builder, tmp_path, on_event=receive)
    assert caught.value is error
    assert events[-1].type == "step_failed"
    assert events[-1].error is error
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("get_operation_status")


@pytest.mark.parametrize("instruction", ["COPY", "ADD"])
@pytest.mark.parametrize("suffix", ["", "FROM base\n"])
async def test_file_finalization_and_stage_sealing_have_distinct_steps(build_case, tmp_path, instruction, suffix):
    client, builder = build_case
    (tmp_path / "Dockerfile").write_text(f"FROM base AS first\n{instruction} data /data\n{suffix}")
    (tmp_path / "data").write_bytes(b"data")
    client.mock("ensure_file", FileResponse(uuid="file", sha256="a" * 64, size=4))
    queue_run(client)
    events = []
    summaries = []
    await build(builder, tmp_path, on_event=events.append, on_step=summaries.append)
    starts = [item.step for item in events if item.type == "step_started"]
    synthetic = [step for step in starts if step.index is None]
    assert len(synthetic) == 1
    assert synthetic[0].keyword == "RUN :"
    assert synthetic[0].parent_id == (2 if suffix else None)
    assert [step.id for step in starts] == list(range(len(starts)))
    assert len(summaries) == (3 if suffix else 2)
    assert [item.step for item in events if item.type == "operation_started"] == synthetic
    assert [item.step for item in events if item.type == "stdout"] == synthetic
    assert client.calls_for("spawn_instance")[0].kwargs["files"]["/data"].uuid == "file"
    assert len(client.calls_for("follow_operation_events")) == 1
    assert all(item.type != "step_failed" for item in events)


def test_sync_output_arrives_before_completion_on_the_build_thread(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nRUN echo live\n")
    client = LiveClient()
    started = threading.Event()
    received = threading.Event()
    callback_threads = set()
    events = []

    def receive(item):
        events.append(item)
        callback_threads.add(threading.get_ident())
        if item.type == "operation_started":
            started.set()
        if item.type == "stdout":
            received.set()

    builder = ContreeDockerBuilder(client)
    with ThreadPoolExecutor() as pool:
        task = pool.submit(builder.build, tmp_path, on_event=receive)
        try:
            assert started.wait(2)
            client.streams["op-1"].put(output("stdout", b"live"))
            assert received.wait(2)
            assert not task.done()
            assert not client.calls_for("get_operation_status")
        finally:
            client.streams["op-1"].put(event("completion"))
        assert task.result(2) == "image-op-1"
    assert len(callback_threads) == 1
    assert events[-1].type == "step_completed"
    assert len(client.calls_for("follow_operation_events")) == 1


async def test_async_output_arrives_before_completion_on_the_build_task(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nRUN echo live\n")
    client = LiveAsyncClient()
    started = asyncio.Event()
    received = asyncio.Event()
    callback_tasks = set()

    async def receive(item):
        callback_tasks.add(asyncio.current_task())
        if item.type == "operation_started":
            started.set()
        if item.type == "stdout":
            received.set()

    task = asyncio.create_task(ContreeAsyncDockerBuilder(client).build(tmp_path, on_event=receive))
    try:
        await asyncio.wait_for(started.wait(), 2)
        await client.streams["op-1"].put(output("stdout", b"live"))
        await asyncio.wait_for(received.wait(), 2)
        assert not task.done()
        assert not client.calls_for("get_operation_status")
    finally:
        await client.streams["op-1"].put(event("completion"))
    assert await asyncio.wait_for(task, 2) == "image-op-1"
    assert callback_tasks == {task}
    assert len(client.calls_for("follow_operation_events")) == 1


async def test_async_cancellation_during_event_wait_cancels_remote(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nRUN sleep 100\n")
    client = LiveAsyncClient()
    started = asyncio.Event()
    events = []

    def receive(item):
        events.append(item)
        if item.type == "operation_started":
            started.set()

    builder = ContreeAsyncDockerBuilder(client)
    task = asyncio.create_task(builder.build(tmp_path, on_event=receive))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events[-1].type == "step_failed"
    # Python 3.10 can create a new CancelledError when a cancelled Task is awaited.
    assert isinstance(events[-1].error, asyncio.CancelledError)
    assert len(client.calls_for("cancel_operation")) == 1
    assert builder.ctx is not None
    assert builder.ctx.progress.current is None


def test_sync_interruption_cancels_remote(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nRUN sleep 100\n")
    client = LiveClient()
    events = []

    def receive(item):
        events.append(item)
        if item.type == "operation_started":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt) as caught:
        ContreeDockerBuilder(client).build(tmp_path, on_event=receive)
    assert events[-1].type == "step_failed"
    assert events[-1].error is caught.value
    assert len(client.calls_for("cancel_operation")) == 1


def test_sync_effective_run_timeout_cancels_stalled_stream(tmp_path):
    from contree_sdk import ContreeSession

    class ShortTimeoutSession(ContreeSession):
        def prepare_request(self, request):
            return replace(super().prepare_request(request), timeout=0.01)

    (tmp_path / "Dockerfile").write_text("FROM base\nRUN sleep 100\n")
    client = LiveClient()
    events = []
    builder = ContreeDockerBuilder(client, session_factory=ShortTimeoutSession)
    with pytest.raises(TimeoutError) as caught:
        builder.build(tmp_path, on_event=events.append)
    assert events[-1].type == "step_failed"
    assert events[-1].error is caught.value
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("get_operation_status")


async def test_async_effective_run_timeout_cancels_stalled_stream(tmp_path):
    from contree_sdk import ContreeAsyncSession

    class ShortTimeoutSession(ContreeAsyncSession):
        def prepare_request(self, request):
            return replace(super().prepare_request(request), timeout=0.01)

    (tmp_path / "Dockerfile").write_text("FROM base\nRUN sleep 100\n")
    client = LiveAsyncClient()
    events = []
    builder = ContreeAsyncDockerBuilder(client, session_factory=ShortTimeoutSession)
    with pytest.raises(asyncio.TimeoutError) as caught:
        await asyncio.wait_for(builder.build(tmp_path, on_event=events.append), 2)
    assert events[-1].type == "step_failed"
    assert events[-1].error is caught.value
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("get_operation_status")


@pytest.mark.parametrize("suffix", ["", "FROM base\n"])
async def test_synthetic_step_failure_has_its_own_identity(build_case, tmp_path, suffix):
    client, builder = build_case
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY data /data\n" + suffix)
    (tmp_path / "data").write_bytes(b"data")
    client.mock("ensure_file", FileResponse(uuid="file", sha256="a" * 64, size=4))
    queue_run(client, exit_code=3)
    events = []
    with pytest.raises(DockerBuildError) as caught:
        await build(builder, tmp_path, on_event=events.append)
    failures = [item for item in events if item.type == "step_failed"]
    assert len(failures) == (2 if suffix else 1)
    assert failures[0].step.keyword == "RUN :"
    assert failures[0].step.index is None
    assert failures[0].operation_uuid == "op-1"
    assert all(item.error is caught.value for item in failures)
    if suffix:
        assert failures[1].step.id == failures[0].step.parent_id
