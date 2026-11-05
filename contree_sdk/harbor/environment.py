"""Harbor environments executing commands and transfers in an SDK V2 lazy VM."""

from __future__ import annotations

import inspect
import math
import sys
import tarfile
from contextlib import AsyncExitStack, aclosing
from functools import cached_property
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from contree_client.httpx import ContreeAsyncClient as HttpxAsyncClient
from contree_client.models import InstanceResultState, StreamRepr
from contree_client.profiles import Profile
from contree_client.types import ContreeAsyncClient
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.environments.definition import COMPOSE_FILE_NAME, DOCKERFILE_NAME, should_upload_environment_dir
from harbor.models.trial.paths import EnvironmentPaths

from contree_sdk import AsyncLazySession, RunRequest, async_import_image, create_async_sandbox_session
from contree_sdk.file_io import run_file_io, write_download_async
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.session.cleanup import await_cleanup


_OUTPUT_LIMIT = 10 * 1024 * 1024


def extract_directory_archive(archive_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        archive.extractall(target_dir, filter="data")


class ConTreeEnvironment(BaseEnvironment):
    """Harbor backend using a restartable AsyncLazySession.

    Idle snapshots preserve files but terminate background processes. An injected
    low-level async client remains caller-owned.
    """

    SNAPSHOT_IDLE_SEC = 20 * 60

    def __init__(
        self,
        *args,
        snapshot_idle_sec: float | None = None,
        contree_profile: str | Profile | None = None,
        contree_client: ContreeAsyncClient | None = None,
        **kwargs,
    ) -> None:
        if snapshot_idle_sec is None:
            snapshot_idle_sec = self.SNAPSHOT_IDLE_SEC
        if not math.isfinite(snapshot_idle_sec) or snapshot_idle_sec <= 0:
            raise ValueError("snapshot_idle_sec must be finite and positive")
        unknown = kwargs.keys() - inspect.signature(BaseEnvironment.__init__).parameters.keys()
        if unknown:
            raise TypeError(f"Unknown ConTree environment options: {', '.join(sorted(unknown))}")
        self._contree_profile = contree_profile
        self._snapshot_idle_sec = snapshot_idle_sec
        self._contree_client = contree_client
        self._stack = AsyncExitStack()
        self._lazy_session: AsyncLazySession | None = None
        self._closing = False
        super().__init__(*args, **kwargs)

    @staticmethod
    def type() -> str:
        return "contree"

    @cached_property
    def capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities()

    @classmethod
    def resource_capabilities(cls) -> EnvironmentResourceCapabilities:
        return EnvironmentResourceCapabilities()

    def _validate_definition(self) -> None:
        config = self.task_env_config
        if not config.docker_image:
            raise ValueError("ConTree requires [environment].docker_image; build and publish Dockerfiles separately.")
        if (self.environment_dir / COMPOSE_FILE_NAME).exists():
            raise ValueError("ConTree does not support Docker Compose environments.")
        if config.gpu_types:
            raise ValueError("ConTree does not support GPU types.")
        if config.mcp_servers:
            raise ValueError("ConTree does not yet support task MCP servers.")
        self.validate_network_policy_support(config.resolve_baseline())
        self._validate_mounts()

        # TODO(CONTREE-243): Forward Harbor resource settings when the SDK supports LazySession VM resources.

    def _validate_mounts(self) -> None:
        # Harbor requests host bind mounts for standard logs; cloud backends transfer these paths instead.
        paths = EnvironmentPaths()
        allowed = {
            str(paths.agent_dir): self.trial_paths.agent_dir,
            str(paths.user_agent_dir): self.trial_paths.user_agent_dir,
            str(paths.verifier_dir): self.trial_paths.verifier_dir,
            str(paths.artifacts_dir): self.trial_paths.artifacts_dir / "logs" / "artifacts",
        }
        # Only these exact writable log mounts can use Harbor's upload/download workflow.
        for mount in self._mounts:
            expected = allowed.get(mount["target"])
            if (
                expected is None
                or mount["type"] != "bind"
                or mount.get("read_only")
                or Path(mount["source"]).resolve() != expected.resolve()
            ):
                raise ValueError("ConTree supports Harbor log transfers, but not custom host mounts.")

    def _require_lazy(self) -> AsyncLazySession:
        if self._lazy_session is None or self._closing:
            raise RuntimeError("ConTree environment is not running; call start() first.")
        return self._lazy_session

    async def start(self, force_build: bool) -> None:
        if self._lazy_session is not None:
            raise RuntimeError("ConTree environment is already started.")

        if force_build and (self.environment_dir / DOCKERFILE_NAME).exists():
            raise ValueError("ConTree cannot force-build a Dockerfile; use the prebuilt docker_image.")
        self._closing = False
        try:
            await self._start()
        except BaseException:
            self._lazy_session = None
            await self._stack.__aexit__(*sys.exc_info())
            raise

    async def _start(self) -> None:
        client = self._contree_client

        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise RuntimeError("ConTree startup requires a prebuilt image.")

        contree_image = await self._import_image(client, docker_image)

        policy = IdleSnapshotPolicy(self._snapshot_idle_sec)
        self._lazy_session = await self._stack.enter_async_context(
            create_async_sandbox_session(
                image=contree_image,
                session_id=self.session_id,
                client=client,
                profile=self._contree_profile if client is None else None,
                client_type=HttpxAsyncClient if client is None else None,
                session_kwargs={"snapshot_policy": policy},
            )
        )

        paths = EnvironmentPaths()
        dirs = [str(paths.agent_dir), str(paths.verifier_dir), str(paths.artifacts_dir)]
        if self.task_env_config.workdir:
            dirs.append(self.task_env_config.workdir)
        dirs.extend(self._mount_targets(writable_only=True))
        result = await self._execute(self._ensure_dirs_command(dirs), cwd="/")
        self._check_result(result, "Creating Harbor log directories")

        if should_upload_environment_dir(self.environment_dir, docker_image=docker_image):
            workdir = self.task_env_config.workdir
            if not workdir:
                result = await self._execute("pwd")
                self._check_result(result, "Resolving image workdir")
                workdir = (result.stdout or "/").strip()
            await self._upload_dir(self.environment_dir, workdir)

    async def _import_image(self, client: ContreeAsyncClient | None, source: str) -> str:
        return await async_import_image(
            source,
            client=client,
            profile=self._contree_profile if client is None else None,
            client_type=HttpxAsyncClient if client is None else None,
        )

    async def stop(self, delete: bool = True) -> None:
        """Cancel the active VM and release resources; delete is ignored."""
        self._closing = True
        try:
            if self._lazy_session is not None:
                await await_cleanup(self._lazy_session.abort())
        finally:
            self._lazy_session = None
            await await_cleanup(self._stack.aclose())

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        user = self._resolve_user(user)

        if isinstance(user, str):
            if user == "root":
                uid = 0
            else:
                raise ValueError(f"ConTree does not support switching users by name (requested {user!r}).")
        else:
            uid = user

        return await self._execute(
            command,
            cwd=cwd,
            env=env,
            uid=uid,
            timeout_sec=timeout_sec,
        )

    async def _execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        uid: int | None = None,
        gid: int | None = None,
        timeout_sec: float | None = None,
    ) -> ExecResult:
        lazy = self._require_lazy()
        if timeout_sec is not None and (not math.isfinite(timeout_sec) or timeout_sec <= 0):
            raise ValueError("Command timeout must be finite and positive.")
        request = RunRequest(
            command="/bin/bash",
            args=("-c", command),
            env=self._merge_env(env),
            cwd=cwd if cwd is not None else self.task_env_config.workdir,
            truncate_output_at=_OUTPUT_LIMIT,
            timeout=timeout_sec,
            uid=uid,
            gid=gid,
        )

        result = await lazy.execute(request)

        if not isinstance(result.state, InstanceResultState) or not isinstance(result.state.exit_code, int):
            raise TypeError("ConTree subprocess returned no exit code")
        for stream in (result.stdout, result.stderr):
            if isinstance(stream, StreamRepr) and stream.truncated is True:
                self.logger.warning("ConTree command output was truncated at %s bytes per stream.", _OUTPUT_LIMIT)
        return ExecResult(
            stdout=result.stdout.as_text() if isinstance(result.stdout, StreamRepr) else "",
            stderr=result.stderr.as_text() if isinstance(result.stderr, StreamRepr) else "",
            return_code=result.state.exit_code,
        )

    @staticmethod
    def _check_result(result: ExecResult, action: str) -> None:
        if result.return_code:
            raise RuntimeError(f"{action} failed (exit {result.return_code}): {result.stderr or result.stdout}")

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        await self._require_lazy().run("true", files={target_path: source_path})

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        await self._require_lazy().run("true", files={target_dir: source_dir})

    @staticmethod
    def _remote_path(path: str) -> PurePosixPath:
        destination = PurePosixPath(path)
        if not destination.is_absolute() or "\0" in path:
            raise ValueError("file paths must be absolute and contain no NUL characters")
        return destination

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        self._remote_path(source_path)
        view = await self._require_lazy().inspect()
        await view.download_file(source_path, target_path)

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        self._remote_path(source_dir)
        view = await self._require_lazy().inspect()
        with TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "download.tar"
            async with aclosing(view.archive(source_dir)) as chunks:
                await write_download_async(chunks, archive_path, path=source_dir)
            await run_file_io(extract_directory_archive, archive_path, Path(target_dir))
