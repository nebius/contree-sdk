import io
import tarfile

import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeClient

from contree_sdk.cache import SyncMemoryCache, SyncSQLiteCache
from contree_sdk.docker import ContreeDockerBuilder
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.store import SyncMemoryStore, SyncSQLiteStore
from tests.unit.session.factories import operation_response, spawn_response


@pytest.fixture
def client() -> ContreeClient:
    client = ContreeClient()
    client.mock("resolve_image", "img-uuid-0")
    return client


def write_dockerfile(tmp_path, text: str) -> None:
    (tmp_path / "Dockerfile").write_text(text)


def test_simple_build(tmp_path, client: ContreeClient):
    write_dockerfile(tmp_path, "FROM tag:python:3.11\nRUN echo hi\n")
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

    builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
    image = builder.build(tmp_path, session_id="sess")

    assert image == "img-uuid-1"
    assert len(client.calls_for("spawn_instance")) == 1
    assert builder.session is not None
    entries, _ = builder.session.history()
    assert [entry.kind for entry in entries] == ["use", "run"]


def test_missing_from_raises(tmp_path, client: ContreeClient):
    write_dockerfile(tmp_path, "RUN echo hi\n")
    builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
    with pytest.raises(ValueError, match="FROM"):
        builder.build(tmp_path, session_id="sess")


def test_run_nonzero_exit_raises_docker_build_error(tmp_path, client: ContreeClient):
    write_dockerfile(tmp_path, "FROM tag:python:3.11\nRUN false\n")
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=1, stdout="", stderr="boom"))

    builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
    with pytest.raises(DockerBuildError, match="boom"):
        builder.build(tmp_path, session_id="sess")


def test_tag_applied_on_success(tmp_path, client: ContreeClient):
    write_dockerfile(tmp_path, "FROM tag:python:3.11\nRUN echo hi\n")
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    client.mock("update_image_tag", None)

    builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
    builder.build(tmp_path, session_id="sess", tag="myapp:latest")

    calls = client.calls_for("update_image_tag")
    assert len(calls) == 1
    assert calls[0].args == ("img-uuid-1", "myapp:latest")


class TestCache:
    def test_second_identical_build_is_full_cache_hit(self, tmp_path, client: ContreeClient):
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nRUN echo hi\n")
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        store = SyncMemoryStore()
        cache = SyncMemoryCache()
        image1 = ContreeDockerBuilder(client, store=store, cache=cache).build(tmp_path, session_id="sess")
        image2 = ContreeDockerBuilder(client, store=store, cache=cache).build(tmp_path, session_id="sess")

        assert image1 == image2
        assert len(client.calls_for("spawn_instance")) == 1

    def test_no_cache_forces_rebuild(self, tmp_path, client: ContreeClient):
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nRUN echo hi\n")
        client.mock("spawn_instance", spawn_response("op-1"))
        client.mock("spawn_instance", spawn_response("op-2"))
        client.mock("wait_operation", operation_response(operation_uuid="op-1", result_image_uuid="img-1", exit_code=0))
        client.mock("wait_operation", operation_response(operation_uuid="op-2", result_image_uuid="img-2", exit_code=0))

        store = SyncMemoryStore()
        cache = SyncMemoryCache()
        ContreeDockerBuilder(client, store=store, cache=cache).build(tmp_path, session_id="sess")
        ContreeDockerBuilder(client, store=store, cache=cache).build(tmp_path, session_id="sess", no_cache=True)

        assert len(client.calls_for("spawn_instance")) == 2


class TestCopy:
    def test_local_file_rides_next_run(self, tmp_path, client: ContreeClient):
        (tmp_path / "app.py").write_text("print(1)\n")
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nCOPY app.py /app.py\nRUN echo hi\n")
        client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=10))
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
        builder.build(tmp_path, session_id="sess")

        assert len(client.calls_for("spawn_instance")) == 1
        call = client.calls_for("spawn_instance")[0]
        files = call.kwargs["files"]
        assert files["/app.py"].uuid == "file-uuid-1"
        assert files["/app.py"].mode == "0644"

    def test_chown_chmod(self, tmp_path, client: ContreeClient):
        (tmp_path / "app.sh").write_text("echo hi\n")
        write_dockerfile(
            tmp_path, "FROM tag:python:3.11\nCOPY --chown=1000:1000 --chmod=0755 app.sh /app.sh\nRUN echo hi\n"
        )
        client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=10))
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
        builder.build(tmp_path, session_id="sess")

        call = client.calls_for("spawn_instance")[0]
        spec = call.kwargs["files"]["/app.sh"]
        assert (spec.uid, spec.gid, spec.mode) == (1000, 1000, "0755")


class TestMultistage:
    def test_copy_from_alias(self, tmp_path):
        client = ContreeClient()
        write_dockerfile(
            tmp_path,
            "FROM tag:builder AS builder\nRUN echo build\n"
            "FROM tag:runtime\nCOPY --from=builder /out /out\nRUN echo done\n",
        )
        client.mock("resolve_image", "img-uuid-builder")
        client.mock("resolve_image", "img-uuid-runtime")
        client.mock("spawn_instance", spawn_response("op-1"))
        client.mock("spawn_instance", spawn_response("op-2"))
        client.mock(
            "wait_operation", operation_response(operation_uuid="op-1", result_image_uuid="img-build", exit_code=0)
        )
        client.mock(
            "wait_operation", operation_response(operation_uuid="op-2", result_image_uuid="img-final", exit_code=0)
        )

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"binary"
            info = tarfile.TarInfo(name="out")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        client.mock("inspect_image_archive", [buf.read()])
        client.mock("ensure_file", FileResponse(uuid="tar-uuid", sha256="tarsha", size=6))

        builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
        image = builder.build(tmp_path, session_id="sess-multi")

        assert image == "img-final"
        # "echo build", the COPY --from extraction RUN, and "echo done"
        assert len(client.calls_for("spawn_instance")) == 3


class TestAddUrl:
    def test_etag_dedup_across_builds(self, tmp_path, client: ContreeClient):
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nADD https://example.com/f.txt /f.txt\nRUN echo hi\n")
        client.mock("ensure_file", FileResponse(uuid="url-file-uuid", sha256="urlsha", size=11))
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        calls = {"n": 0}

        def fake_http_fetch(url, method, headers):
            calls["n"] += 1
            return [("ETag", "abc123")], [b"hello world"]

        store = SyncMemoryStore()
        cache = SyncMemoryCache()
        ContreeDockerBuilder(client, store=store, cache=cache, http_fetch=fake_http_fetch).build(
            tmp_path, session_id="sess-add"
        )
        assert calls["n"] == 1
        assert len(client.calls_for("ensure_file")) == 1

        ContreeDockerBuilder(client, store=store, cache=cache, http_fetch=fake_http_fetch).build(
            tmp_path, session_id="sess-add", no_cache=True
        )
        assert calls["n"] == 2
        # ETag cache hit: no additional ensure_file call for the URL body
        assert len(client.calls_for("ensure_file")) == 1


class TestEnvWorkdirUser:
    def test_env_workdir_user_thread_into_run(self, tmp_path, client: ContreeClient):
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nENV FOO=bar\nWORKDIR /app\nUSER 1000\nRUN echo hi\n")
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        builder = ContreeDockerBuilder(client, store=SyncMemoryStore(), cache=SyncMemoryCache())
        builder.build(tmp_path, session_id="sess")

        call = client.calls_for("spawn_instance")[0]
        assert call.args[0] == "su -s /bin/sh -c 'echo hi' 1000"
        assert call.kwargs["env"] == {"FOO": "bar"}
        assert call.kwargs["cwd"] == "/app"


class TestArgCacheBusting:
    def test_same_build_args_is_cache_hit(self, tmp_path, client: ContreeClient):
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nARG VERSION=3.11\nRUN echo hi\n")
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        store = SyncMemoryStore()
        cache = SyncMemoryCache()
        ContreeDockerBuilder(client, store=store, cache=cache).build(
            tmp_path, session_id="sess", build_args={"VERSION": "3.11"}
        )
        ContreeDockerBuilder(client, store=store, cache=cache).build(
            tmp_path, session_id="sess", build_args={"VERSION": "3.11"}
        )

        assert len(client.calls_for("spawn_instance")) == 1

    def test_different_build_args_is_cache_miss(self, tmp_path, client: ContreeClient):
        # RUN's own text never references ${VERSION} - only the ARG's *value* differs,
        # proving the chain hash is sensitive to declared-arg state, not just command text
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nARG VERSION=3.11\nRUN echo hi\n")
        client.mock("spawn_instance", spawn_response("op-1"))
        client.mock("spawn_instance", spawn_response("op-2"))
        client.mock("wait_operation", operation_response(operation_uuid="op-1", result_image_uuid="img-1", exit_code=0))
        client.mock("wait_operation", operation_response(operation_uuid="op-2", result_image_uuid="img-2", exit_code=0))

        store = SyncMemoryStore()
        cache = SyncMemoryCache()
        ContreeDockerBuilder(client, store=store, cache=cache).build(
            tmp_path, session_id="sess", build_args={"VERSION": "3.11"}
        )
        ContreeDockerBuilder(client, store=store, cache=cache).build(
            tmp_path, session_id="sess", build_args={"VERSION": "3.12"}
        )

        assert len(client.calls_for("spawn_instance")) == 2


class TestSqlitePersistence:
    def test_cache_hit_across_fresh_store_and_cache_instances(self, tmp_path, client: ContreeClient):
        (tmp_path / "app.py").write_text("print(1)\n")
        write_dockerfile(tmp_path, "FROM tag:python:3.11\nCOPY app.py /app.py\nRUN echo hi\n")
        client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=10))
        client.mock("spawn_instance", spawn_response())
        client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

        store_path = tmp_path / "store.db"
        cache_path = tmp_path / "cache.db"

        store1 = SyncSQLiteStore(store_path)
        cache1 = SyncSQLiteCache(cache_path)
        ContreeDockerBuilder(client, store=store1, cache=cache1).build(tmp_path, session_id="sess")
        store1.close()
        cache1.close()

        store2 = SyncSQLiteStore(store_path)
        cache2 = SyncSQLiteCache(cache_path)
        ContreeDockerBuilder(client, store=store2, cache=cache2).build(tmp_path, session_id="sess")
        store2.close()
        cache2.close()

        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("ensure_file")) == 1
