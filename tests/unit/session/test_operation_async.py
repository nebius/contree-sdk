import asyncio
import io
from datetime import datetime, timezone

import pytest
from contree_client.models import (
    EventDataSizeCap,
    EventDataStream,
    FileSpec,
    InstanceResult,
    OperationEvent,
    OperationEventType,
    StreamRepr,
)
from contree_client.testing import ContreeAsyncClient

from contree_sdk.execution import OperationContext, RunRequest
from contree_sdk.session import AsyncSubprocessHandle
from contree_sdk.session.base import or_none
from contree_sdk.session.operation_async import AsyncOperation
from tests.unit.session.factories import mock_completion, operation_response
from tests.unit.session.lazy_clients import event as live_event


@pytest.fixture
def client() -> ContreeAsyncClient:
    return ContreeAsyncClient()


def make_event(id: int, type: OperationEventType, spid, data=None) -> OperationEvent:  # noqa: A002
    if data is None and type in {"spawn", "exit"}:
        data = live_event(type, spid).data
    return OperationEvent(
        id=id, ts=datetime.now(timezone.utc), type=type, data=data if data is not None else {}, spid=spid
    )


def make_stream_event(id: int, type: OperationEventType, spid: int, text: str) -> OperationEvent:  # noqa: A002
    return make_event(id, type, spid, EventDataStream(value=text, encoding="ascii"))


def exit_code_of(result: InstanceResult) -> int | None:
    state = or_none(result.state)
    return None if state is None else or_none(state.exit_code)


class TestSimpleMode:
    async def test_apply_files_applies_prepared_references(self, client: ContreeAsyncClient):
        client.mock("apply_instance_file", None)
        context = OperationContext(RunRequest(command="sleep"), "session", "image", "root", "main")
        operation = AsyncOperation(client, "op-1", context=context)

        await operation.apply_files({"/work/input": FileSpec(uuid="file-1")})

        call = client.calls_for("apply_instance_file")[0]
        assert call.args == ("op-1", "file-1", "/work/input")
        assert call.kwargs == {"replace": True}
        assert operation.files == ()
        assert operation.context is not None
        assert operation.context is context
        assert operation.context.files == ()

    async def test_apply_files_validates_all_references_before_applying(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")

        with pytest.raises(ValueError, match="cannot set uid, gid, or mode"):
            await operation.apply_files({"/ok": FileSpec(uuid="file-1"), "/bad": FileSpec(uuid="file-2", mode=0o755)})

        assert client.calls_for("apply_instance_file") == []

    async def test_wait_uses_shared_stream_and_returns_instance_result(self, client: ContreeAsyncClient):
        mock_completion(client, operation_response(result_image_uuid="img-1", exit_code=0, stdout="hi\n"))
        operation = AsyncOperation(client, "op-1")

        result = await operation.wait()

        stdout = or_none(result.stdout)
        assert stdout is not None
        assert stdout.as_text() == "hi\n"
        assert operation.response is not None
        assert operation.response.result_image_uuid == "img-1"
        assert client.calls_for("wait_operation") == []
        call = client.calls_for("follow_operation_events")[0]
        assert call.args[0] == "op-1"

    async def test_status_forwards_to_get_operation_status(self, client: ContreeAsyncClient):
        client.mock("get_operation_status", operation_response(result_image_uuid="img-1"))
        operation = AsyncOperation(client, "op-1")

        response = await operation.status(inflight=True)

        assert response.result_image_uuid == "img-1"
        call = client.calls_for("get_operation_status")[0]
        assert call.args[0] == "op-1"
        assert call.kwargs["inflight"] is True

    async def test_send_stdin_encodes_text_as_ascii(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_stdin", None)
        operation = AsyncOperation(client, "op-1")

        await operation.send_stdin("hello\n")

        call = client.calls_for("operation_subprocess_stdin")[0]
        assert call.args == ("op-1", 1, "hello\n")
        assert call.kwargs["encoding"] == "ascii"
        assert call.kwargs["close"] is True

    async def test_send_stdin_encodes_bytes_as_base64(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_stdin", None)
        operation = AsyncOperation(client, "op-1")

        await operation.send_stdin(b"\x00\x01", spid=2, close=False)

        call = client.calls_for("operation_subprocess_stdin")[0]
        assert call.args[0] == "op-1"
        assert call.args[1] == 2
        assert call.kwargs["encoding"] == "base64"
        assert call.kwargs["close"] is False

    async def test_signal_forwards_to_operation_subprocess_kill(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_kill", None)
        operation = AsyncOperation(client, "op-1")

        await operation.signal("SIGINT", spid=2)

        call = client.calls_for("operation_subprocess_kill")[0]
        assert call.args == ("op-1", 2)
        assert call.kwargs["signal"] == "SIGINT"

    async def test_cancel_forwards_to_cancel_operation(self, client: ContreeAsyncClient):
        client.mock("cancel_operation", None)
        operation = AsyncOperation(client, "op-1")

        await operation.cancel()

        assert client.calls_for("cancel_operation")[0].args == ("op-1",)

    async def test_events_forwards_to_follow_operation_events(self, client: ContreeAsyncClient):
        events = [make_event(1, "stdout", 1), make_event(2, "completion", ...)]
        client.mock("follow_operation_events", events)
        operation = AsyncOperation(client, "op-1")

        collected = [event async for event in operation.events()]

        assert collected == events

    async def test_bare_operation_reattaches_by_uuid_alone(self, client: ContreeAsyncClient):
        # every method is stateless per-UUID, so reattaching after a process restart
        # is just constructing a new handle with the same UUID - no extra state needed
        mock_completion(client, operation_response(result_image_uuid="img-1"))
        operation = AsyncOperation(client, "op-1")

        result = await operation.wait()

        assert result is not None


class TestShutdown:
    async def test_shutdown_is_a_noop_once_terminal(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")
        operation.terminal = True

        await operation.shutdown()

        assert client.calls_for("operation_subprocess_kill") == []
        assert client.calls_for("cancel_operation") == []

    @pytest.mark.parametrize("cancel_first", [False, True])
    async def test_shutdown_without_reader_does_not_wait(self, client, monkeypatch, cancel_first):
        client.mock("cancel_operation", None)
        operation = AsyncOperation(client, "op-1")

        async def unexpected_wait(*args, **kwargs):
            pytest.fail("shutdown waited without an event reader")

        monkeypatch.setattr(operation.terminal_event, "wait", unexpected_wait)
        if cancel_first:
            await operation.cancel()
        await operation.shutdown()
        await operation.shutdown()

        assert len(client.calls_for("cancel_operation")) == 1
        assert client.calls_for("operation_subprocess_kill") == []
        assert client.calls_for("follow_operation_events") == []
        assert not operation.terminal  # An accepted cancellation is not a completion event.

    async def test_shutdown_retries_failed_cancel(self, client):
        client.mock("cancel_operation", error=OSError("cancel failed"))
        client.mock("cancel_operation", None)
        operation = AsyncOperation(client, "op-1")
        with pytest.raises(OSError, match="cancel failed"):
            await operation.shutdown()
        assert not operation.cancel_requested

        await operation.shutdown()
        await operation.shutdown()
        assert len(client.calls_for("cancel_operation")) == 2

    async def test_shutdown_signals_then_cancels_if_deadline_passes(self, client, monkeypatch):
        released = asyncio.Event()

        class WaitingOperation(AsyncOperation):
            async def open_event_stream(self):
                await released.wait()
                yield make_event(1, "completion", ...)

        async def cancel(uuid):
            released.set()

        monkeypatch.setattr(client, "cancel_operation", cancel)
        client.mock("operation_subprocess_kill", None)
        async with WaitingOperation(client, "op-1", shutdown_timeout=0.05) as operation:
            pass

        signal_call = client.calls_for("operation_subprocess_kill")[0]
        assert signal_call.args == ("op-1", 1)
        assert signal_call.kwargs["signal"] == "SIGTERM"
        assert operation.cancel_requested
        assert operation.terminal


class TestRichMode:
    async def test_run_outside_with_block_raises(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")
        with pytest.raises(RuntimeError, match="context manager"):
            await operation.run("echo hi")

    async def test_enter_starts_consumer_task(self, client: ContreeAsyncClient):
        client.mock("follow_operation_events", [make_event(1, "completion", ...)])
        # the pump task may or may not have already observed `completion` by the
        # time the `async with` block exits (a real race) - mock the escalation
        # path too so either outcome of that race succeeds
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        async with AsyncOperation(client, "op-1") as operation:
            assert operation.consumer_task is not None

    async def test_run_spawns_subprocess_and_demuxes_its_events(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_create", 2)
        # exit-time race guard: see test_enter_starts_consumer_task
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
            make_event(0, "spawn", 2),
            make_stream_event(1, "stdout", 1, "main output\n"),
            make_stream_event(2, "stdout", 2, "sub output\n"),
            make_event(3, "exit", 2),
            make_event(4, "completion", ...),
        ]
        client.mock("follow_operation_events", events)

        async with AsyncOperation(client, "op-1") as operation:
            handle = await operation.run("echo sub")
            collected = [event async for event in handle]
            result = await handle.wait()

        assert [event.id for event in collected] == [0, 2, 3]
        assert client.calls_for("operation_subprocess") == []
        assert isinstance(result.stdout, StreamRepr)
        assert result.stdout.as_text() == "sub output\n"
        assert exit_code_of(result) == 0
        create_call = client.calls_for("operation_subprocess_create")[0]
        assert create_call.args == ("op-1", "echo sub")

    async def test_subprocess_await_unblocks_when_operation_completes_without_its_exit(
        self, client: ContreeAsyncClient
    ):
        # spid=1 finished (and the whole operation completed) before the spawned
        # subprocess's own exit event ever arrived - the handle must not hang forever
        client.mock("operation_subprocess_create", 2)
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
            make_event(0, "spawn", 2),
            make_stream_event(1, "stdout", 2, "partial\n"),
            make_event(2, "completion", ...),
        ]
        client.mock("follow_operation_events", events)

        async with AsyncOperation(client, "op-1") as operation:
            handle = await operation.run("sleep 100")
            with pytest.raises(RuntimeError, match="incomplete"):
                await handle
        assert client.calls_for("operation_subprocess") == []

    async def test_pipe_to_writes_decoded_chunks_to_text_and_binary_streams(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_create", 2)
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
            make_event(0, "spawn", 2),
            make_stream_event(1, "stdout", 2, "out\n"),
            make_stream_event(2, "stderr", 2, "err\n"),
            make_event(3, "exit", 2),
            make_event(4, "completion", ...),
        ]
        client.mock("follow_operation_events", events)

        text_out = io.StringIO()
        binary_err = io.BytesIO()
        async with AsyncOperation(client, "op-1") as operation:
            handle = await operation.run("echo")
            result = await handle.pipe_to(stdout=text_out, stderr=binary_err)

        assert text_out.getvalue() == "out\n"
        assert binary_err.getvalue() == b"err\n"
        assert exit_code_of(result) == 0

    async def test_exit_signals_then_waits_then_joins_consumer(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [make_event(1, "completion", ...)]
        client.mock("follow_operation_events", events)

        async with AsyncOperation(client, "op-1", shutdown_timeout=2) as operation:
            pass

        assert operation.terminal is True
        assert operation.consumer_task is not None
        assert operation.consumer_task.done()


class TestClaimQueue:
    # deterministic regression coverage for the pump()/run() race: pump() can observe
    # a spid's events (including its own exit) before run() gets to register a queue
    # for it, so claim_queue() must flush anything buffered rather than dropping it -
    # exercised here directly, without depending on real task scheduling to reproduce
    async def test_claim_queue_flushes_events_buffered_before_registration(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")
        buffered = asyncio.Queue()
        buffered.put_nowait(make_stream_event(1, "stdout", 2, "sub output\n"))
        buffered.put_nowait(make_event(2, "exit", 2))
        operation.pending_events[2] = buffered

        subprocess_queue = await operation.claim_queue(2)

        first = subprocess_queue.get_nowait()
        second = subprocess_queue.get_nowait()
        assert first is not None
        assert second is not None
        assert first.id == 1
        assert second.id == 2
        assert 2 not in operation.pending_events
        assert operation.queues[2] is subprocess_queue

    async def test_claim_queue_closes_handle_immediately_if_already_terminal(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")
        operation.terminal = True

        subprocess_queue = await operation.claim_queue(2)

        assert subprocess_queue.get_nowait() is None
        assert 2 not in operation.queues


async def test_wait_after_consuming_exit_and_repeated_wait_do_not_block(client):
    operation = AsyncOperation(client, "op-1")
    events = asyncio.Queue()
    events.put_nowait(make_event(0, "spawn", 2))
    events.put_nowait(make_event(1, "exit", 2, live_event("exit", 2, exit_code=7).data))
    handle = AsyncSubprocessHandle(operation, 2, events)
    assert len([event async for event in handle]) == 2
    first = await handle.wait(timeout=0.01)
    second = await handle.wait(timeout=0.01)
    assert first is second
    assert exit_code_of(first) == 7
    assert client.calls_for("operation_subprocess") == []


async def test_stream_failure_is_delivered_to_subprocess_waiter(client):
    client.mock("follow_operation_events", [], error=OSError("stream disconnected"))
    operation = AsyncOperation(client, "op-1")
    events = await operation.claim_queue(2)
    await operation.pump()
    handle = AsyncSubprocessHandle(operation, 2, events)
    with pytest.raises(OSError, match="stream disconnected"):
        await handle.wait(timeout=0.01)


async def test_wait_failure_cancels_operation_and_preserves_original_error(client):
    mock_completion(client, error=TimeoutError("original timeout"))
    client.mock("cancel_operation", error=OSError("cleanup failed"))
    with pytest.raises(TimeoutError, match="original timeout"):
        await AsyncOperation(client, "op-1").wait()
    assert len(client.calls_for("cancel_operation")) == 1


async def test_main_output_is_not_buffered_without_a_subprocess_consumer(client):
    client.mock("follow_operation_events", [make_stream_event(1, "stdout", 1, "data")])
    operation = AsyncOperation(client, "op-1")
    await operation.pump()
    assert operation.pending_events == {}


async def test_cancelled_wait_cancels_remote_operation(client):
    mock_completion(client, error=asyncio.CancelledError())
    client.mock("cancel_operation", None)
    with pytest.raises(asyncio.CancelledError):
        await AsyncOperation(client, "op-1").wait()
    assert len(client.calls_for("cancel_operation")) == 1


class CustomAsyncSubprocess(AsyncSubprocessHandle):
    pass


class EventOverrideOperation(AsyncOperation):
    async def open_event_stream(self):
        try:
            yield make_event(0, "spawn", 2)
            yield make_stream_event(1, "stdout", 2, "custom stream\n")
            yield make_event(2, "exit", 2)
            yield make_event(3, "completion", ...)
        finally:
            self.source_closed = True

    def create_subprocess(self, spid, events_queue):
        return CustomAsyncSubprocess(self, spid, events_queue)


async def test_rich_mode_uses_public_event_and_subprocess_hooks(client):
    client.mock("operation_subprocess_create", 2)
    async with EventOverrideOperation(client, "op-1") as operation:
        assert operation.consumer_task is not None
        await operation.consumer_task
        handle = await operation.run("echo")
        assert isinstance(handle, CustomAsyncSubprocess)
        output = io.BytesIO()
        assert exit_code_of(await handle.pipe_to(stdout=output)) == 0
        assert exit_code_of(await handle.wait()) == 0
    assert operation.source_closed
    assert output.getvalue() == b"custom stream\n"
    assert client.calls_for("follow_operation_events") == []
    assert client.calls_for("operation_subprocess") == []


async def test_wait_preserves_output_consumed_by_partial_iteration(client):
    operation = AsyncOperation(client, "op-1")
    events = asyncio.Queue()
    for event in (
        make_event(0, "spawn", 2),
        make_stream_event(1, "stdout", 2, "before"),
        make_stream_event(2, "stdout", 2, " after"),
        make_stream_event(3, "stderr", 2, "warning"),
        make_event(4, "exit", 2),
    ):
        events.put_nowait(event)
    handle = AsyncSubprocessHandle(operation, 2, events)
    iterator = handle.iterate()
    assert (await anext(iterator)).type == "spawn"
    assert (await anext(iterator)).type == "stdout"
    result = await handle.wait(timeout=1)
    assert isinstance(result.stdout, StreamRepr)
    assert isinstance(result.stderr, StreamRepr)
    assert result.stdout.as_text() == "before after"
    assert result.stderr.as_text() == "warning"
    assert await handle.pipe_to() is result
    assert client.calls_for("operation_subprocess") == []


@pytest.mark.parametrize("claim_first", [False, True])
@pytest.mark.parametrize("cap_first", [False, True])
async def test_global_size_cap_marks_existing_and_future_subprocess_output(client, claim_first, cap_first):
    cap = make_event(2, "size_cap", None, EventDataSizeCap(limit_bytes=100, file_size=100))
    events = [make_event(0, "spawn", 2), make_stream_event(1, "stdout", 2, "partial")]
    events.insert(0 if cap_first else len(events), cap)
    events.extend((make_event(3, "exit", 2), make_event(4, "completion", None)))
    client.mock("follow_operation_events", events)
    operation = AsyncOperation(client, "op-1")
    if claim_first:
        subprocess_queue = await operation.claim_queue(2)
    await operation.pump()
    if not claim_first:
        subprocess_queue = await operation.claim_queue(2)
    handle = AsyncSubprocessHandle(operation, 2, subprocess_queue)
    result = await handle.wait(timeout=1)
    assert isinstance(result.stdout, StreamRepr)
    assert isinstance(result.stderr, StreamRepr)
    assert result.stdout.as_text() == "partial"
    assert result.stdout.truncated is True
    assert result.stderr.truncated is True
    assert client.calls_for("operation_subprocess") == []


async def test_malformed_stream_error_is_preserved_for_repeated_wait(client):
    operation = AsyncOperation(client, "op-1")
    events = asyncio.Queue()
    events.put_nowait(make_event(0, "spawn", 2))
    events.put_nowait(make_event(1, "stdout", 2, EventDataStream(value="??", encoding="base64")))
    events.put_nowait(make_event(2, "exit", 2))
    handle = AsyncSubprocessHandle(operation, 2, events)
    for timeout in (1, 2):
        with pytest.raises(RuntimeError, match="invalid subprocess stdout"):
            await handle.wait(timeout=timeout)
    assert client.calls_for("operation_subprocess") == []
