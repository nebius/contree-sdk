"""Operations created inside session helpers cannot outlive their failed waits."""

import asyncio
import threading

import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession, RunRequest
from contree_sdk.cache import AsyncMemoryCache, SyncMemoryCache
from contree_sdk.docker.context import AsyncBuildContext, BuildContext
from contree_sdk.docker.local_context import LocalContext
from contree_sdk.exceptions import SessionConflictError
from contree_sdk.session import AsyncOperation, Operation
from tests.unit.session.factories import mock_completion, operation_response, spawn_response
from tests.unit.session.test_detached import call


@pytest.mark.parametrize("cancel_wait", [False, True], ids=["timeout", "cancel"])
@pytest.mark.parametrize("cancel_fails", [False, True])
@pytest.mark.parametrize("workflow", ["detached", "run", "execute", "docker"])
async def test_owned_wait_joins_its_reader(cancel_wait, cancel_fails, workflow, tmp_path):
    started = asyncio.Event()
    closed = asyncio.Event()
    handles = []

    class WaitingOperation(AsyncOperation):
        async def open_event_stream(self):
            try:
                started.set()
                await asyncio.Event().wait()
                yield  # pragma: no cover
            finally:
                closed.set()

    class Session(ContreeAsyncSession):
        def create_operation(self, response, context):
            operation = WaitingOperation(
                self.client,
                response.uuid,
                context=context,
                timeout=context.request.timeout_seconds,
                shutdown_timeout=0.01,
            )
            handles.append(operation)
            return operation

    client = ContreeAsyncClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    client.mock("cancel_operation", error=OSError("cancel failed") if cancel_fails else None)
    client.mock("operation_subprocess_kill", None)
    session = Session(client, image="base")
    timeout = None if cancel_wait else 0.01
    record = await session.spawn_detached("sleep", disposable=False) if workflow == "detached" else None

    async def wait():
        request = RunRequest(command="sleep", disposable=False, timeout=timeout)
        if workflow == "detached":
            assert record is not None
            await session.wait_operation(record.uuid, timeout=timeout)
        elif workflow == "run":
            await session.run("sleep", disposable=False, timeout=timeout)
        elif workflow == "execute":
            await session.execute(request)
        else:
            context = AsyncBuildContext(
                client, session.store, AsyncMemoryCache(), LocalContext(tmp_path), session=session
            )
            await context.run_operation(request, branch="layer")

    task = asyncio.create_task(wait())
    await asyncio.wait_for(started.wait(), 1)
    if cancel_wait:
        task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError if cancel_wait else asyncio.TimeoutError):
            await task
        assert closed.is_set()
        assert handles[-1].consumer_task.done()
        if record is not None:
            assert (await session.store.get_operation(session.session_id, record.uuid)).pending
        assert len((await session.history())[0]) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if handles[-1].consumer_task is not None:
            handles[-1].consumer_task.cancel()
            await asyncio.gather(handles[-1].consumer_task, return_exceptions=True)


@pytest.mark.parametrize("cancel_fails", [False, True])
@pytest.mark.parametrize("workflow", ["detached", "run", "execute", "docker"])
def test_sync_owned_wait_calls_shutdown_before_returning(cancel_fails, workflow, tmp_path):
    release = threading.Event()
    handles = []

    class WaitingOperation(Operation):
        def open_event_stream(self):
            assert release.wait(2)
            return iter(())

        def shutdown(self):
            release.set()
            super().shutdown()

    class Session(ContreeSession):
        def create_operation(self, response, context):
            operation = WaitingOperation(
                self.client,
                response.uuid,
                context=context,
                timeout=context.request.timeout_seconds,
                shutdown_timeout=0.1,
            )
            handles.append(operation)
            return operation

    client = ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    client.mock("cancel_operation", error=OSError("cancel failed") if cancel_fails else None)
    client.mock("operation_subprocess_kill", None)
    session = Session(client, image="base")
    record = session.spawn_detached("sleep", disposable=False) if workflow == "detached" else None

    def wait():
        request = RunRequest(command="sleep", disposable=False, timeout=0.01)
        if workflow == "detached":
            assert record is not None
            session.wait_operation(record.uuid, timeout=0.01)
        elif workflow == "run":
            session.run("sleep", disposable=False, timeout=0.01)
        elif workflow == "execute":
            session.execute(request)
        else:
            context = BuildContext(client, session.store, SyncMemoryCache(), LocalContext(tmp_path), session=session)
            context.run_operation(request, branch="layer")

    try:
        with pytest.raises(TimeoutError):
            wait()
        assert release.is_set()
        assert not handles[-1].consumer_thread.is_alive()
        if record is not None:
            assert session.store.get_operation(session.session_id, record.uuid).pending
        assert len(session.history()[0]) == 1
    finally:
        release.set()
        if handles[-1].consumer_thread is not None:
            handles[-1].consumer_thread.join(2)


async def test_repeated_cancellation_waits_for_reader_cleanup():
    started = asyncio.Event()
    stopping = asyncio.Event()
    release = asyncio.Event()
    handles = []

    class WaitingOperation(AsyncOperation):
        async def open_event_stream(self):
            started.set()
            await asyncio.Event().wait()
            yield  # pragma: no cover

        async def shutdown(self):
            stopping.set()
            await release.wait()
            await super().shutdown()

    class Session(ContreeAsyncSession):
        def create_operation(self, response, context):
            operation = WaitingOperation(self.client, response.uuid, context=context, shutdown_timeout=0.01)
            handles.append(operation)
            return operation

    client = ContreeAsyncClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    client.mock("cancel_operation", None)
    session = Session(client, image="base")
    record = await session.spawn_detached("sleep", disposable=False)
    task = asyncio.create_task(session.wait_operation(record.uuid))
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(stopping.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert handles[-1].consumer_task.done()
        assert (await session.store.get_operation(session.session_id, record.uuid)).pending
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if handles[-1].consumer_task is not None:
            handles[-1].consumer_task.cancel()
            await asyncio.gather(handles[-1].consumer_task, return_exceptions=True)


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_cancellation_during_successful_scope_cleanup_is_propagated(cleanup_fails):
    from contree_sdk.session.cleanup import owned_async_operation

    stopping = asyncio.Event()
    release = asyncio.Event()
    stopped = asyncio.Event()

    class SlowShutdown(AsyncOperation):
        async def shutdown(self):
            stopping.set()
            await release.wait()
            stopped.set()
            if cleanup_fails:
                raise OSError("cleanup failed")

    async def use_operation():
        async with owned_async_operation(SlowShutdown(ContreeAsyncClient(), "op")):
            pass

    task = asyncio.create_task(use_operation())
    try:
        await asyncio.wait_for(stopping.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("workflow", ["detached", "run", "execute", "docker"])
@pytest.mark.parametrize("commit_fails", [False, True])
async def test_completed_handle_is_closed_before_commit(asynchronous, workflow, commit_fails, monkeypatch, tmp_path):
    closed = []
    handles = []

    class SyncHandle(Operation):
        def shutdown(self):
            super().shutdown()
            closed.append(self.uuid)

    class AsyncHandle(AsyncOperation):
        async def shutdown(self):
            await super().shutdown()
            closed.append(self.uuid)

    class SyncSession(ContreeSession):
        def create_operation(self, response, context):
            operation = SyncHandle(self.client, response.uuid, context=context)
            handles.append(operation)
            return operation

    class AsyncSession(ContreeAsyncSession):
        def create_operation(self, response, context):
            operation = AsyncHandle(self.client, response.uuid, context=context)
            handles.append(operation)
            return operation

    client = ContreeAsyncClient() if asynchronous else ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    session = (
        AsyncSession(client, image="base")
        if isinstance(client, ContreeAsyncClient)
        else SyncSession(client, image="base")
    )
    if isinstance(session, ContreeAsyncSession):
        await session.ensure_ready()
    record = await call(session, "spawn_detached", "true", disposable=False) if workflow == "detached" else None

    def fail_commit(*args, **kwargs):
        assert closed == ["op-1"]
        raise SessionConflictError("concurrent history change")

    async def fail_async_commit(*args, **kwargs):
        fail_commit(*args, **kwargs)

    if commit_fails:
        method = "finish_operation" if workflow == "detached" else "append"
        monkeypatch.setattr(session.store, method, fail_async_commit if asynchronous else fail_commit)

    async def run():
        request = RunRequest(command="true", disposable=False)
        if record is not None:
            return await call(session, "wait_operation", record.uuid)
        if workflow == "run":
            return await call(session, "run", "true", disposable=False)
        if workflow == "execute":
            return await call(session, "execute", request)
        context = (
            AsyncBuildContext(
                session.client, session.store, AsyncMemoryCache(), LocalContext(tmp_path), session=session
            )
            if isinstance(session, ContreeAsyncSession)
            else BuildContext(session.client, session.store, SyncMemoryCache(), LocalContext(tmp_path), session=session)
        )
        return await call(context, "run_operation", request, branch="layer")

    if commit_fails:
        with pytest.raises(SessionConflictError, match="concurrent history change"):
            await run()
    else:
        await run()
    assert closed == ["op-1"]
    assert not client.calls_for("cancel_operation")
    assert len(client.calls_for("follow_operation_events")) == 1
    operation = handles[-1]
    if isinstance(operation, AsyncOperation):
        assert operation.consumer_task.done()
    else:
        assert not operation.consumer_thread.is_alive()
