"""Harbor environments executing commands and transfers in an SDK V2 lazy VM."""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import tarfile
from collections.abc import Callable, Iterator
from contextlib import AsyncExitStack, aclosing, contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from time import monotonic

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

    def __init__(
        self,
        *args,
        snapshot_idle_sec: float = 20 * 60,
        contree_profile: str | Profile | None = None,
        contree_client: ContreeAsyncClient | None = None,
        **kwargs,
    ) -> None:
        if not math.isfinite(snapshot_idle_sec) or snapshot_idle_sec <= 0:
            raise ValueError("snapshot_idle_sec must be finite and positive")
        unknown = kwargs.keys() - inspect.signature(BaseEnvironment.__init__).parameters.keys()
        if unknown:
            raise TypeError(f"Unknown ConTree environment options: {', '.join(sorted(unknown))}")
        self.contree_profile = contree_profile
        self._snapshot_idle_sec = snapshot_idle_sec
        self.contree_client = contree_client
        self.stack = AsyncExitStack()
        self._lazy_session: AsyncLazySession | None = None
        self._lock = asyncio.Lock()
        self._closing = False
        super().__init__(*args, **kwargs)

    @staticmethod
    def type() -> str:
        return "contree"

    @property
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
        if not math.isfinite(config.build_timeout_sec) or config.build_timeout_sec <= 0:
            raise ValueError("build_timeout_sec must be finite and positive")
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

    def _log_debug(self, message: str, *args: object) -> None:
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        lazy = self._lazy_session
        operation = lazy.operation if lazy is not None else None
        context = operation.context if operation is not None else None
        snapshot = lazy.last_entry if lazy is not None else None
        # Harbor's logger routes these records to its per-trial and job file handlers.
        self.logger.debug(
            "%s ConTree session=%s phase=%s operation=%s image=%s snapshot_operation=%s snapshot_image=%s " + message,
            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            self.session_id,
            lazy.phase if lazy is not None else None,
            operation.uuid if operation is not None else None,
            context.image_uuid if context is not None else None,
            snapshot.operation_uuid if snapshot is not None else None,
            snapshot.image_uuid if snapshot is not None else None,
            *args,
        )

    @contextmanager
    def _log_action(self, action: str) -> Iterator[None]:
        started = monotonic()
        self._log_debug("%s started", action)
        try:
            yield
        except BaseException as error:
            self._log_debug(
                "%s failed elapsed_sec=%.3f error_type=%s", action, monotonic() - started, type(error).__name__
            )
            raise
        else:
            self._log_debug("%s finished elapsed_sec=%.3f", action, monotonic() - started)

    def snapshot_timer(self, seconds: float, callback: Callable[[], None]) -> asyncio.TimerHandle:
        self._log_debug("idle snapshot timer armed idle_sec=%s", seconds)

        def expired() -> None:
            self._log_debug("idle snapshot timer expired idle_sec=%s", seconds)
            callback()

        return asyncio.get_running_loop().call_later(seconds, expired)

    async def start(self, force_build: bool) -> None:
        with self._log_action("start"):
            async with self._lock:
                if self._lazy_session is not None:
                    raise RuntimeError("ConTree environment is already started.")
                if force_build and (self.environment_dir / DOCKERFILE_NAME).exists():
                    raise ValueError("ConTree cannot force-build a Dockerfile; use the prebuilt docker_image.")
                self._closing = False
                try:
                    await asyncio.wait_for(self._start(), timeout=self.task_env_config.build_timeout_sec)
                except BaseException:
                    if self._lazy_session is not None:
                        with suppress(Exception, asyncio.CancelledError):
                            await await_cleanup(self._lazy_session.abort())
                    self._lazy_session = None
                    await await_cleanup(self.stack.aclose())
                    raise

    async def _start(self) -> None:
        startup_deadline = asyncio.get_running_loop().time() + self.task_env_config.build_timeout_sec
        client = self.contree_client

        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise RuntimeError("ConTree startup requires a prebuilt image.")
        self._log_debug("configuration snapshot_idle_sec=%s", self._snapshot_idle_sec)
        with self._log_action("import_image"):
            contree_image = await self._import_image(client, docker_image)
            self._log_debug("import_image resolved image=%s", contree_image)

        policy = IdleSnapshotPolicy(self._snapshot_idle_sec, timer_factory=self.snapshot_timer)
        startup_timeout = startup_deadline - asyncio.get_running_loop().time()
        if startup_timeout <= 0:
            raise TimeoutError("ConTree environment startup timed out while resolving its image")

        self._lazy_session = await self.stack.enter_async_context(
            create_async_sandbox_session(
                image=contree_image,
                session_id=self.session_id,
                client=client,
                profile=self.contree_profile if client is None else None,
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
            timeout=math.ceil(self.task_env_config.build_timeout_sec),
            client=client,
            profile=self.contree_profile if client is None else None,
            client_type=HttpxAsyncClient if client is None else None,
        )

    async def stop(self, delete: bool = True) -> None:
        """Cancel the active VM and release resources; delete is ignored."""
        with self._log_action("stop"):
            self._log_debug("stop requested delete=%s", delete)
            self._closing = True
            session = self._lazy_session
            try:
                if session is not None:
                    await await_cleanup(session.abort())
            finally:
                async with self._lock:
                    self._lazy_session = None
                    await await_cleanup(self.stack.aclose())

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

        async with self._lock:
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

        with self._log_action("exec"):
            self._log_debug("exec options cwd=%s uid=%s gid=%s timeout_sec=%s", request.cwd, uid, gid, timeout_sec)
            result = await lazy.execute(request)

            if not isinstance(result.state, InstanceResultState) or not isinstance(result.state.exit_code, int):
                raise TypeError("ConTree subprocess returned no exit code")
            self._log_debug("exec result return_code=%s", result.state.exit_code)
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
        async with self._lock:
            with self._log_action(f"upload_file source={source_path} target={target_path}"):
                await self._require_lazy().run("true", files={target_path: source_path})

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        async with self._lock:
            await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        with self._log_action(f"upload_dir source={source_dir} target={target_dir}"):
            await self._require_lazy().run("true", files={target_dir: source_dir})

    @staticmethod
    def _remote_path(path: str) -> PurePosixPath:
        destination = PurePosixPath(path)
        if not destination.is_absolute() or "\0" in path:
            raise ValueError("file paths must be absolute and contain no NUL characters")
        return destination

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        async with self._lock:
            with self._log_action(f"download_file source={source_path} target={target_path}"):
                self._remote_path(source_path)
                view = await self._require_lazy().inspect()
                await view.download_file(source_path, target_path)

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        async with self._lock:
            with self._log_action(f"download_dir source={source_dir} target={target_dir}"):
                self._remote_path(source_dir)
                view = await self._require_lazy().inspect()
                with TemporaryDirectory() as temporary:
                    archive_path = Path(temporary) / "download.tar"
                    async with aclosing(view.archive(source_dir)) as chunks:
                        await write_download_async(chunks, archive_path, path=source_dir)
                    await run_file_io(extract_directory_archive, archive_path, Path(target_dir))
