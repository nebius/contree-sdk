import inspect
from io import BytesIO, StringIO

import pytest
from contree_client.models import StreamRepr

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


class AsyncReader:
    closed = False

    async def read(self, size=-1):
        return b"async\x00\xff"


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("lazy", [False, True], ids=["regular", "lazy"])
@pytest.mark.parametrize("source_kind", ["text", "bytes", "path", "text_stream", "binary_stream", "async_stream"])
async def test_session_reads_stdin_sources_without_file_transfer(asynchronous, lazy, source_kind, tmp_path):
    if source_kind == "text":
        source = "hello 🌎"
        expected = source.encode()
    elif source_kind == "bytes":
        source = expected = b"hello\x00\xff"
    elif source_kind == "path":
        source = tmp_path / "stdin"
        expected = b"file\x00\xff"
        source.write_bytes(expected)
    elif source_kind == "text_stream":
        source = StringIO("skip hello 🌎")
        source.seek(5)
        expected = "hello 🌎".encode()
    elif source_kind == "binary_stream":
        source = BytesIO(b"skip hello\x00\xff")
        source.seek(5)
        expected = b"hello\x00\xff"
    else:
        source = AsyncReader()
        expected = b"async\x00\xff"

    client = LiveAsyncClient() if asynchronous else LiveClient()
    base = (ContreeAsyncSession if asynchronous else ContreeSession)(client, image="base")
    session = (AsyncLazySession if asynchronous else LazySession)(base) if lazy else base
    operation = None
    try:
        if source_kind == "async_stream" and not asynchronous:
            with pytest.raises(TypeError, match="requires an async session"):
                await invoke(session.spawn, "cat", stdin=source)
            assert not client.calls_for("spawn_instance")
        else:
            operation = await invoke(session.spawn, "cat", stdin=source)
            calls = client.calls_for("operation_subprocess_create" if lazy else "spawn_instance")
            stdin = calls[-1].kwargs["stdin"]
            assert StreamRepr(value=stdin.value, encoding=stdin.encoding).as_bytes() == expected
        assert not client.calls_for("ensure_file")
        if hasattr(source, "closed"):
            assert not source.closed
    finally:
        if lazy:
            await invoke(session.abort)
        elif operation is not None:
            await invoke(operation.shutdown)
