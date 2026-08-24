import io
from datetime import datetime, timezone

import pytest
from contree_client.models import (
    EventDataStream,
    InstanceResult,
    InstanceResultState,
    OperationEvent,
    OperationEventType,
)
from contree_client.testing import ContreeAsyncClient

from contree_sdk.session.base import or_none
from contree_sdk.session.operation_async import AsyncOperation
from tests.unit.session.factories import operation_response


@pytest.fixture
def client() -> ContreeAsyncClient:
    return ContreeAsyncClient()


def make_event(id: int, type: OperationEventType, spid, data=None) -> OperationEvent:  # noqa: A002
    return OperationEvent(
        id=id, ts=datetime.now(timezone.utc), type=type, data=data if data is not None else {}, spid=spid
    )


def make_stream_event(id: int, type: OperationEventType, spid: int, text: str) -> OperationEvent:  # noqa: A002
    return make_event(id, type, spid, EventDataStream(value=text, encoding="ascii"))


def exit_code_of(result: InstanceResult) -> int | None:
    state = or_none(result.state)
    return None if state is None else or_none(state.exit_code)


class TestSimpleMode:
    async def test_wait_forwards_to_wait_operation_and_returns_instance_result(self, client: ContreeAsyncClient):
        client.mock("wait_operation", operation_response(result_image_uuid="img-1", exit_code=0, stdout="hi\n"))
        operation = AsyncOperation(client, "op-1")

        result = await operation.wait()

        stdout = or_none(result.stdout)
        assert stdout is not None
        assert stdout.as_text() == "hi\n"
        assert operation.response is not None
        assert operation.response.result_image_uuid == "img-1"
        call = client.calls_for("wait_operation")[0]
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
        client.mock("wait_operation", operation_response(result_image_uuid="img-1"))
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

    async def test_shutdown_signals_then_cancels_if_deadline_passes(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        operation = AsyncOperation(client, "op-1", shutdown_timeout=0.05)

        await operation.shutdown()

        signal_call = client.calls_for("operation_subprocess_kill")[0]
        assert signal_call.args == ("op-1", 1)
        assert signal_call.kwargs["signal"] == "SIGTERM"
        assert len(client.calls_for("cancel_operation")) == 1


class TestRichMode:
    async def test_run_outside_with_block_raises(self, client: ContreeAsyncClient):
        operation = AsyncOperation(client, "op-1")
        with pytest.raises(RuntimeError, match="context manager"):
            await operation.run("echo hi")

    async def test_enter_starts_consumer_task(self, client: ContreeAsyncClient):
        client.mock("follow_operation_events", [make_event(1, "completion", ...)])
        client.mock("wait_operation", operation_response())
        # the pump task may or may not have already observed `completion` by the
        # time the `async with` block exits (a real race) - mock the escalation
        # path too so either outcome of that race succeeds
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        async with AsyncOperation(client, "op-1") as operation:
            assert operation.consumer_task is not None

    async def test_run_spawns_subprocess_and_demuxes_its_events(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_create", 2)
        client.mock("operation_subprocess", InstanceResult(state=InstanceResultState(exit_code=0)))
        # exit-time race guard: see test_enter_starts_consumer_task
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
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

        assert [event.id for event in collected] == [2, 3]
        assert exit_code_of(result) == 0
        create_call = client.calls_for("operation_subprocess_create")[0]
        assert create_call.args == ("op-1", "echo sub")

    async def test_subprocess_await_unblocks_when_operation_completes_without_its_exit(
        self, client: ContreeAsyncClient
    ):
        # spid=1 finished (and the whole operation completed) before the spawned
        # subprocess's own exit event ever arrived - the handle must not hang forever
        client.mock("operation_subprocess_create", 2)
        client.mock("operation_subprocess", InstanceResult(state=InstanceResultState(exit_code=-1)))
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
            make_stream_event(1, "stdout", 2, "partial\n"),
            make_event(2, "completion", ...),
        ]
        client.mock("follow_operation_events", events)

        async with AsyncOperation(client, "op-1") as operation:
            handle = await operation.run("sleep 100")
            result = await handle

        assert exit_code_of(result) == -1

    async def test_pipe_to_writes_decoded_chunks_to_text_and_binary_streams(self, client: ContreeAsyncClient):
        client.mock("operation_subprocess_create", 2)
        client.mock("operation_subprocess", InstanceResult(state=InstanceResultState(exit_code=0)))
        client.mock("operation_subprocess_kill", None)
        client.mock("cancel_operation", None)
        events = [
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
