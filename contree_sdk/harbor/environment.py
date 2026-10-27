"""Harbor environments executing commands and transfers in an SDK V2 lazy VM."""

from __future__ import annotations

import asyncio
import codecs
import inspect
import math
from contextlib import suppress
from pathlib import Path
from typing import Literal

from contree_client.httpx import ContreeAsyncClient as HttpxAsyncClient
from contree_client.models import EventDataStream, InstanceResult, InstanceResultState, StreamRepr
from contree_client.types import ContreeAsyncClient
from harbor.environments.base import BaseEnvironment, ExecResult, OutputCallback
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.environments.definition import COMPOSE_FILE_NAME, DOCKERFILE_NAME, should_upload_environment_dir
from harbor.models.trial.paths import EnvironmentPaths

from contree_sdk import AsyncLazySession, RunRequest, async_import_image, create_async_sandbox_session
from contree_sdk.sandbox import AsyncSandboxSessionContext
from contree_sdk.session.cleanup import await_cleanup
from contree_sdk.session.contracts import AsyncOperationContract, AsyncSubprocessContract
from contree_sdk.session.defaults import KEEPALIVE_SLEEP_SECONDS
from contree_sdk.session.snapshot_policy import IdleSnapshotPolicy, ManualSnapshotPolicy


_OUTPUT_LIMIT = 10 * 1024 * 1024
_TRANSFER_TIMEOUT = 600


class ConTreeEnvironment(BaseEnvironment):
    """Harbor backend using a restartable AsyncLazySession.

    By default the VM stays alive throughout a trial, including file transfers.
    Set snapshot_idle_sec to opt into idle snapshots and subsequent VM restart;
    those boundaries preserve files but terminate background processes. An
    injected low-level async client remains caller-owned.
    """

    def __init__(
        self,
        *args,
        profile: str | None = None,
        operation_timeout: float = 1000,
        snapshot_idle_sec: float | None = None,
        snapshot_timeout: float = 120,
        terminate_timeout: float = 5,
        vm_timeout: float = 3600,
        client: ContreeAsyncClient | None = None,
        **kwargs,
    ) -> None:
        for name, value in (
            ("operation_timeout", operation_timeout),
            ("snapshot_timeout", snapshot_timeout),
            ("terminate_timeout", terminate_timeout),
            ("snapshot_idle_sec", snapshot_idle_sec),
            ("vm_timeout", vm_timeout),
        ):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be finite and positive")
        unknown = kwargs.keys() - inspect.signature(BaseEnvironment.__init__).parameters.keys()
        if unknown:
            raise TypeError(f"Unknown ConTree environment options: {', '.join(sorted(unknown))}")
        self._profile = profile
        self._operation_timeout = operation_timeout
        self._snapshot_idle_sec = snapshot_idle_sec
        self._snapshot_timeout = snapshot_timeout
        self._terminate_timeout = terminate_timeout
        self._vm_timeout = vm_timeout
        self._client = client
        self._provided_client = client
        self._lazy_session_context: AsyncSandboxSessionContext[AsyncLazySession] | None = None
        self._lazy_session: AsyncLazySession | None = None
        self._lock = asyncio.Lock()
        self._active_run: asyncio.Task[InstanceResult] | None = None
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

        if config.cpus is not None or config.memory_mb is not None or config.storage_mb is not None:
            # ConTree doesn't enforce resources.
            pass

    def _validate_mounts(self) -> None:
        paths = EnvironmentPaths()
        allowed = {
            str(paths.agent_dir): self.trial_paths.agent_dir,
            str(paths.user_agent_dir): self.trial_paths.user_agent_dir,
            str(paths.verifier_dir): self.trial_paths.verifier_dir,
            str(paths.artifacts_dir): self.trial_paths.artifacts_dir / "logs" / "artifacts",
        }
        # Harbor supplies its log mounts even for cloud environments. Only
        # those exact mounts can be replaced by its non-mounted copy workflow.
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
                await self._close_session_context()
                raise

    async def _start(self) -> None:
        startup_deadline = asyncio.get_running_loop().time() + self.task_env_config.build_timeout_sec
        client = self._client

        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise RuntimeError("ConTree startup requires a prebuilt image.")
        contree_image = await self._import_image(client, docker_image)

        policy = (
            ManualSnapshotPolicy() if self._snapshot_idle_sec is None else IdleSnapshotPolicy(self._snapshot_idle_sec)
        )
        startup_timeout = startup_deadline - asyncio.get_running_loop().time()
        if startup_timeout <= 0:
            raise TimeoutError("ConTree environment startup timed out while resolving its image")

        self._lazy_session_context = create_async_sandbox_session(
            image=contree_image,
            session_id=self.session_id,
            client=client,
            profile=self._profile if client is None else None,
            client_type=HttpxAsyncClient if client is None else None,
            session_kwargs={
                "vm_request": RunRequest(
                    command="sleep", args=(str(KEEPALIVE_SLEEP_SECONDS),), timeout=self._vm_timeout
                ),
                "snapshot_policy": policy,
                "snapshot_timeout": self._snapshot_timeout,
                "startup_timeout": startup_timeout,
            },
        )
        self._lazy_session = await self._lazy_session_context.__aenter__()  # noqa: PLC2801 - spans Harbor start/stop
        self._client = self._lazy_session.session.client

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
            profile=self._profile if client is None else None,
            client_type=HttpxAsyncClient if client is None else None,
        )

    async def _close_session_context(self) -> None:
        context, self._lazy_session_context = self._lazy_session_context, None
        try:
            if context is not None:
                await context.__aexit__(None, None, None)
        finally:
            self._client = self._provided_client

    async def stop(self, delete: bool = True) -> None:
        """Complete the active operation, save its image, and release resources.

        delete is accepted for Harbor compatibility and has no effect. Images
        are managed by ConTree; stopping does not delete or tag them.
        """
        self._closing = True
        if self._active_run is not None:
            self._active_run.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._active_run
        async with self._lock:
            session = self._lazy_session
            try:
                if session is not None:
                    await session.close(timeout=self._snapshot_timeout)
            finally:
                if session is not None and session.phase != "closed":
                    with suppress(Exception, asyncio.CancelledError):
                        await await_cleanup(session.abort())
                self._lazy_session = None
                await self._close_session_context()

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
                output_callback=self._output_callback(),
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
        output_callback: OutputCallback | None = None,
    ) -> ExecResult:
        lazy = self._require_lazy()
        timeout = self._operation_timeout if timeout_sec is None else timeout_sec
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Command timeout must be finite and positive.")
        request = RunRequest(
            command="/bin/bash",
            args=("-c", command),
            env=self._merge_env(env),
            cwd=cwd if cwd is not None else self.task_env_config.workdir,
            truncate_output_at=_OUTPUT_LIMIT,
            uid=uid,
            gid=gid,
        )
        handle = None
        operation = None

        async def collect() -> InstanceResult:
            nonlocal handle, operation
            handle = await lazy.spawn_request(request)
            operation = lazy.operation
            if operation is None:
                raise RuntimeError("ConTree subprocess has no active operation")
            if output_callback is not None:
                await self._stream_output(handle, output_callback)
            return await handle.wait()

        self._active_run = asyncio.create_task(collect())
        try:
            result = await asyncio.wait_for(self._active_run, timeout=timeout)
        except BaseException:
            if handle is not None and operation is not None:
                with suppress(Exception, asyncio.CancelledError):
                    await await_cleanup(self._terminate(lazy, operation, handle.spid))
            raise
        finally:
            self._active_run = None

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
    async def _stream_output(handle: AsyncSubprocessContract, callback: OutputCallback) -> None:
        decoders: dict[Literal["stdout", "stderr"], codecs.IncrementalDecoder] = {
            name: codecs.getincrementaldecoder("utf-8")("replace") for name in ("stdout", "stderr")
        }
        async for event in handle:
            if event.type in {"stdout", "stderr"} and isinstance(event.data, EventDataStream):
                stream: Literal["stdout", "stderr"] = "stdout" if event.type == "stdout" else "stderr"
                text = decoders[stream].decode(event.data.as_bytes())
                if text:
                    await callback(text, stream)
        for name, decoder in decoders.items():
            if tail := decoder.decode(b"", final=True):
                await callback(tail, name)

    async def _terminate(self, lazy: AsyncLazySession, operation: AsyncOperationContract, spid: int) -> None:
        async def kill_and_confirm() -> None:
            async with lazy.condition:
                if spid not in lazy.state.active or lazy.state.phase == "closed":
                    return
            await operation.signal("SIGKILL", spid=spid)
            async with lazy.condition:
                await lazy.condition.wait_for(lambda: spid not in lazy.state.active or lazy.state.error is not None)
                if lazy.state.error is not None:
                    raise RuntimeError("ConTree VM failed while terminating a command") from lazy.state.error

        try:
            await asyncio.wait_for(kill_and_confirm(), timeout=self._terminate_timeout)
        except BaseException:
            await lazy.abort()
            raise

    @staticmethod
    def _check_result(result: ExecResult, action: str) -> None:
        if result.return_code:
            raise RuntimeError(f"{action} failed (exit {result.return_code}): {result.stderr or result.stdout}")

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        async with self._lock:
            await asyncio.wait_for(
                self._require_lazy().upload_file(source_path, target_path), timeout=_TRANSFER_TIMEOUT
            )

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        async with self._lock:
            await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        await asyncio.wait_for(self._require_lazy().upload_dir(source_dir, target_dir), timeout=_TRANSFER_TIMEOUT)

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        async with self._lock:
            await asyncio.wait_for(
                self._require_lazy().download_file(source_path, target_path), timeout=_TRANSFER_TIMEOUT
            )

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        async with self._lock:
            await asyncio.wait_for(self._require_lazy().download_dir(source_dir, target_dir), timeout=_TRANSFER_TIMEOUT)
