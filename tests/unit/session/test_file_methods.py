import base64
import inspect

import pytest
from contree_client.models import DirectoryList, GrepResult

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=["sync", "async", "lazy-sync", "lazy-async"])
async def session_files(request):
    asynchronous = request.param.endswith("async")
    lazy = request.param.startswith("lazy")
    if asynchronous:
        client = LiveAsyncClient()
        base = ContreeAsyncSession(client, image="base")
        session = AsyncLazySession(base) if lazy else base
    else:
        client = LiveClient()
        base = ContreeSession(client, image="base")
        session = LazySession(base) if lazy else base
    for source in ("image", "instance"):
        client.mock(f"inspect_{source}_list", DirectoryList(path="/work", files=[]))
        client.mock(
            f"inspect_{source}_grep",
            GrepResult(path="/work", patterns=["hello"], matches=[], truncated=True),
        )
        client.mock(f"inspect_{source}_download", b"hello\x00\xff")
    try:
        yield session, client, lazy
    finally:
        if isinstance(session, (AsyncLazySession, LazySession)):
            await invoke(session.abort)


async def test_direct_reads_use_saved_image_without_starting_vm(session_files):
    session, client, _ = session_files
    assert (await invoke(session.list_dir)).path == "/work"
    options = {
        "path": ["/work", "/etc"],
        "glob": ["*.txt", "!secret*"],
        "max_count": 2,
        "max_total": 5,
        "case": "smart",
        "before": 1,
        "after": 3,
    }
    result = await invoke(session.grep, ["hello", "world"], **options)
    assert result.truncated is True
    assert await invoke(session.read_file, "/work/message") == b"hello\x00\xff"
    assert client.calls_for("inspect_image_list")[0].args == ("base", "/")
    assert client.calls_for("inspect_image_grep")[0].args == ("base", ["hello", "world"])
    assert client.calls_for("inspect_image_grep")[0].kwargs == options
    assert not client.calls_for("spawn_instance")


@pytest.mark.parametrize("session_files", ["lazy-sync", "lazy-async"], indirect=True)
async def test_direct_files_follow_live_vm_and_saved_snapshot(session_files):
    session, client, _ = session_files
    await invoke(session.write_file, "/work/message", b"hello\x00\xff")
    assert (await invoke(session.list_dir, "/work")).path == "/work"
    assert (await invoke(session.grep, "hello", path="/work")).truncated is True
    assert await invoke(session.read_file, "/work/message") == b"hello\x00\xff"
    for operation in ("list", "grep", "download"):
        assert client.calls_for(f"inspect_instance_{operation}")[0].args[0] == "op-1"
        assert not client.calls_for(f"inspect_image_{operation}")
    assert not client.calls_for("operation_subprocess_kill")
    assert not client.calls_for("get_operation_status")
    assert len(client.calls_for("spawn_instance")) == 1
    stdin = client.calls_for("operation_subprocess_create")[0].kwargs["stdin"]
    assert stdin.encoding == "base64"
    assert base64.b64decode(stdin.value) == b"hello\x00\xff"
    await invoke(session.snapshot, timeout=2)
    await invoke(session.list_dir, "/work")
    await invoke(session.grep, "hello", path="/work")
    await invoke(session.read_file, "/work/message")
    for operation in ("list", "grep", "download"):
        assert client.calls_for(f"inspect_image_{operation}")[0].args[0] == "image-op-1"


@pytest.mark.parametrize(
    ("method", "endpoint", "args"),
    [
        ("list_dir", "list", ("/missing",)),
        ("grep", "grep", ("invalid pattern",)),
        ("read_file", "download", ("/missing",)),
    ],
)
async def test_direct_file_errors_propagate_without_snapshot_fallback(session_files, method, endpoint, args):
    session, client, lazy = session_files
    if lazy:
        await invoke(session.run, "start")
    source = "instance" if lazy else "image"
    failure = OSError("inspection failed")
    client.mocks[f"inspect_{source}_{endpoint}"].clear()
    client.mock(f"inspect_{source}_{endpoint}", None, error=failure)
    with pytest.raises(OSError, match="inspection failed") as caught:
        await invoke(getattr(session, method), *args)
    assert caught.value is failure
    assert not client.calls_for("operation_subprocess_kill")
    if lazy:
        assert not client.calls_for(f"inspect_image_{endpoint}")
        assert session.state.inspecting == 0
        await invoke(session.run, "still usable")
