"""Independent processes share only SQLite data and explicit node identities."""

import asyncio
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.files import UploadedFile, UploadFileSpec
from contree_sdk.store import AsyncSQLiteStore, Node, NodeConflictError, SyncSQLiteStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response
from tests.unit.store.test_session_tree import session_for
from tests.unit.store.test_tree_store import call


def actor_process(path, root, actor, barrier, output):
    asyncio.run(run_actor(path, root, actor, barrier, output))


async def run_actor(path, root, actor, barrier, output):
    store = AsyncSQLiteStore(path) if actor % 2 else SyncSQLiteStore(path)
    client = ContreeAsyncClient() if isinstance(store, AsyncSQLiteStore) else ContreeClient()
    name = f"actor-{actor}"
    client.mock("spawn_instance", spawn_response(name))
    mock_completion(client, operation_response(operation_uuid=name, result_image_uuid=f"image-{actor}"))
    # Queue both outcomes before the first call; the test client repeats its last outcome.
    client.mock("spawn_instance", spawn_response(name + "-follow"))
    mock_completion(client, operation_response(operation_uuid=name + "-follow", result_image_uuid=f"follow-{actor}"))
    try:
        session = await session_for(store, client, node_id=root)
        await call(session.create_branch, "work")
        await call(session.switch_branch, "work")
        await call(session.set_cwd, f"/actor-{actor}")
        await call(session.set_env, {"ACTOR": name})
        staged = await call(
            session.stage_files, {"/input": UploadFileSpec(source=UploadedFile(uuid=f"upload-{actor}", sha256=name))}
        )
        operation = await call(session.spawn, "work")
        # Every actor captures its context before any actor publishes a result.
        await asyncio.to_thread(barrier.wait, 15)
        if actor == 0:
            await call(session.navigate, root)
        await call(operation.wait)
        entry = await call(session.commit_result, operation)
        assert entry.parent_id == staged.id
        assert session.tip_id == (root if actor == 0 else entry.id)
        sent = client.calls_for("spawn_instance")[0].kwargs
        assert sent["files"]["/input"].uuid == f"upload-{actor}"
        assert sent["env"] == {"ACTOR": name}
        assert sent["cwd"] == f"/actor-{actor}"
        # Several actors publish different proposals for one identity: only one wins.
        await asyncio.to_thread(barrier.wait, 15)
        proposal = Node(id="decision", parent_id=root, kind="decision", data={"actor": actor})
        try:
            await call(store.append, "shared", proposal)
            won = True
        except NodeConflictError:
            won = False
        winner = await call(store.get_node, "shared", "decision")
        # Each actor explicitly continues a result published by another actor.
        peer_name = f"actor-{(actor + 1) % barrier.parties}"
        runs = (await call(store.list_nodes, "shared", kind="run")).items
        peer = next(node for node in runs if node.data["operation_uuid"] == peer_name)
        await call(session.navigate, peer.id)
        await call(session.run, "follow")
        tip = await call(store.get_node, "shared", session.tip_id)
        assert tip.parent_id == peer.id
        assert tip.data["operation_uuid"] == name + "-follow"
        output.put({
            "actor": actor,
            "first": entry.id,
            "staged": staged.id,
            "tip": tip.id,
            "source": peer.id,
            "won": won,
            "winner": winner.data["actor"],
        })
    finally:
        await call(store.close)


@pytest.mark.parametrize("actors", [2, 5])
def test_independent_sync_and_async_processes_share_one_session(tmp_path, actors):
    path = tmp_path / "actors.db"
    with SyncSQLiteStore(path) as store:
        client = ContreeClient()
        client.mock("resolve_image", "base")
        root = ContreeSession(client, store=store, session_id="shared", image="base").tip_id
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(actors)
    output = context.Queue()
    processes = [
        context.Process(target=actor_process, args=(path, root, actor, barrier, output)) for actor in range(actors)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
        assert all(process.exitcode == 0 for process in processes), [process.exitcode for process in processes]
        results = [output.get(timeout=3) for _ in processes]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=3)
        output.close()
        output.join_thread()
    assert sum(result["won"] for result in results) == 1
    assert len({result["winner"] for result in results}) == 1
    with SyncSQLiteStore(path) as observer:
        assert len(observer.list_nodes("shared").items) == 2 + actors * 5
        by_actor = {result["actor"]: result for result in results}
        for result in results:
            actor, tip, staged = result["actor"], result["tip"], result["staged"]
            # A new process can recover each actor's work from explicit identities.
            resumed = ContreeSession(ContreeClient(), store=observer, session_id="shared", node_id=tip)
            assert resumed.image_uuid == f"follow-{actor}"
            assert resumed.env == {"ACTOR": f"actor-{actor}"}
            assert resumed.cwd == f"/actor-{actor}"
            assert not resumed.pending_files()
            resumed.navigate(staged)
            assert resumed.pending_files()[0].uuid == f"upload-{actor}"
            history = observer.list_history("shared", tip).items
            assert len(history) == 6
            assert history[1].id == by_actor[(actor + 1) % actors]["first"]
            assert history[0].parent_id == result["source"]
            assert history[-1].id == root
        with pytest.raises(ValueError, match="node_id"):
            ContreeSession(ContreeClient(), store=observer, session_id="shared")


def test_simultaneous_session_initialization_adopts_one_root(tmp_path, monkeypatch):
    path = tmp_path / "initialization.db"
    barrier = Barrier(3)

    def start():
        with SyncSQLiteStore(path) as store:
            append = store.append

            def gated(session_id, node):
                if node.parent_id is None:
                    barrier.wait(timeout=10)
                append(session_id, node)

            monkeypatch.setattr(store, "append", gated)
            client = ContreeClient()
            client.mock("resolve_image", "base")
            return ContreeSession(client, store=store, session_id="shared", image="base").tip_id

    with ThreadPoolExecutor(3) as workers:
        roots = list(workers.map(lambda _: start(), range(3)))
    assert len(set(roots)) == 1
    with SyncSQLiteStore(path) as observer:
        assert [node.id for node in observer.list_nodes("shared").items] == [roots[0]]


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_lost_append_reply_retries_through_another_connection(tmp_path, monkeypatch, asynchronous):
    path = tmp_path / "retry.db"
    store_type = AsyncSQLiteStore if asynchronous else SyncSQLiteStore
    first, second = store_type(path), store_type(path)
    client = ContreeAsyncClient() if asynchronous else ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    try:
        session = await session_for(first, client, image="base")
        root = session.tip_id
        operation = await call(session.spawn, "work")
        await call(operation.wait)
        append = first.append

        def lost_reply(session_id, node):
            append(session_id, node)
            raise TimeoutError("write committed; acknowledgement lost")

        async def lost_async_reply(session_id, node):
            await call(append, session_id, node)
            raise TimeoutError("write committed; acknowledgement lost")

        monkeypatch.setattr(first, "append", lost_async_reply if asynchronous else lost_reply)
        with pytest.raises(TimeoutError, match="acknowledgement lost"):
            await call(session.commit_result, operation)
        assert session.tip_id == root
        if isinstance(session, ContreeAsyncSession):
            assert isinstance(second, AsyncSQLiteStore)
            session.store = second
        else:
            assert isinstance(second, SyncSQLiteStore)
            session.store = second
        saved = await call(session.commit_result, operation)
        assert saved.id == operation.context.node_id
        assert session.tip_id == saved.id
        assert len((await call(second.list_children, "shared", root)).items) == 1
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await call(first.close)
        await call(second.close)
