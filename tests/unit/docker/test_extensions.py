import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.docker import (
    AsyncBuildContext,
    BuildContext,
    ContreeAsyncDockerBuilder,
    ContreeDockerBuilder,
    DockerfileParser,
    EnvKeyword,
    RunKeyword,
)
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore
from tests.unit.session.factories import operation_response, spawn_response


class CustomEnv(EnvKeyword):
    NAME = "CUSTOMENV"


def make_parser():
    parser = DockerfileParser()
    parser.register(CustomEnv)
    return parser


class CustomContext(BuildContext):
    pass


class CustomAsyncContext(AsyncBuildContext):
    pass


class CustomSession(ContreeSession):
    pass


class CustomAsyncSession(ContreeAsyncSession):
    pass


class CustomBuilder(ContreeDockerBuilder):
    context_class = CustomContext


class CustomAsyncBuilder(ContreeAsyncDockerBuilder):
    context_class = CustomAsyncContext


def test_registry_is_local_and_accepts_whitespace():
    parser = make_parser()
    assert parser.parse("CUSTOMENV\tBUILD_MODE=test") == [CustomEnv.parse("BUILD_MODE=test")]
    with pytest.raises(ValueError, match="unknown"):
        DockerfileParser().parse("CUSTOMENV BUILD_MODE=test")


def test_context_session_and_directive_extensions_survive_cache_hits(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nCUSTOMENV BUILD_MODE=test\nRUN echo hi\n")
    client = ContreeClient()
    client.mock("resolve_image", "base-image")
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response())
    store = SyncMemoryStore()
    for _ in range(2):
        builder = CustomBuilder(client, store=store, parser=make_parser(), session_factory=CustomSession)
        assert builder.build(tmp_path, session_id="custom") == "img-uuid-1"
        assert isinstance(builder.ctx, CustomContext)
        assert isinstance(builder.session, CustomSession)
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["env"] == {"BUILD_MODE": "test"}


async def test_async_context_session_and_directive_extensions_survive_cache_hits(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nCUSTOMENV BUILD_MODE=release\nRUN echo hi\n")
    client = ContreeAsyncClient()
    client.mock("resolve_image", "base-image")
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response())
    store = AsyncMemoryStore()
    for _ in range(2):
        builder = CustomAsyncBuilder(client, store=store, parser=make_parser(), session_factory=CustomAsyncSession)
        assert await builder.build(tmp_path, session_id="custom") == "img-uuid-1"
        assert isinstance(builder.ctx, CustomAsyncContext)
        assert isinstance(builder.session, CustomAsyncSession)
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["env"] == {"BUILD_MODE": "release"}


class NoRunBuilder(ContreeDockerBuilder):
    def execute_directive(self, directive, context):
        if isinstance(directive, RunKeyword):
            raise TypeError("RUN disabled by policy")
        super().execute_directive(directive, context)


class NoRunAsyncBuilder(ContreeAsyncDockerBuilder):
    async def execute_directive(self, directive, context):
        if isinstance(directive, RunKeyword):
            raise TypeError("RUN disabled by policy")
        await super().execute_directive(directive, context)


@pytest.mark.parametrize("next_stage", ["", "FROM base\n"])
def test_final_file_materialization_uses_directive_policy(tmp_path, next_stage):
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY data /data\n" + next_stage)
    (tmp_path / "data").write_bytes(b"data")
    client = ContreeClient()
    client.mock("resolve_image", "base-image")
    client.mock("ensure_file", FileResponse(uuid="file", sha256="a" * 64, size=4))
    with pytest.raises(TypeError, match="RUN disabled by policy"):
        NoRunBuilder(client).build(tmp_path)
    assert client.calls_for("spawn_instance") == []


@pytest.mark.parametrize("next_stage", ["", "FROM base\n"])
async def test_async_final_file_materialization_uses_directive_policy(tmp_path, next_stage):
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY data /data\n" + next_stage)
    (tmp_path / "data").write_bytes(b"data")
    client = ContreeAsyncClient()
    client.mock("resolve_image", "base-image")
    client.mock("ensure_file", FileResponse(uuid="file", sha256="a" * 64, size=4))
    with pytest.raises(TypeError, match="RUN disabled by policy"):
        await NoRunAsyncBuilder(client).build(tmp_path)
    assert client.calls_for("spawn_instance") == []


async def test_async_from_only_build_initializes_custom_session_on_cache_hit_and_miss(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\n")
    client = ContreeAsyncClient()
    client.mock("resolve_image", "base-image")
    store = AsyncMemoryStore()
    for _ in range(2):
        builder = ContreeAsyncDockerBuilder(client, store=store, session_factory=CustomAsyncSession)
        assert await builder.build(tmp_path, session_id="from-only") == "base-image"
        assert isinstance(builder.session, CustomAsyncSession)
        assert builder.session.ready
    assert client.calls_for("spawn_instance") == []
