"""Harbor environments executing commands and transfers in an SDK V2 lazy VM."""

from __future__ import annotations

import asyncio
import codecs
import inspect
import math
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from contree_client.exceptions import APIConnectionError
from contree_client.httpx import ContreeAsyncClient as HttpxAsyncClient
from contree_client.models import EventDataStream, InstanceResult, InstanceResultState, StreamRepr
from contree_client.types import ContreeAsyncClient
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.environments.definition import COMPOSE_FILE_NAME, DOCKERFILE_NAME, should_upload_environment_dir
from harbor.models.trial.paths import EnvironmentPaths

from contree_sdk import (
    AsyncLazySession,
    ContreeAsyncSession,
    RunRequest,
    async_import_image,
    create_async_sandbox_session,
)
from contree_sdk.sandbox import AsyncSandboxSessionContext
from contree_sdk.session.cleanup import await_cleanup
from contree_sdk.session.contracts import AsyncOperationContract
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
        self._sandbox: AsyncSandboxSessionContext[AsyncLazySession] | None = None
        self._session: ContreeAsyncSession | None = None
        self._lazy: AsyncLazySession | None = None
        self._lock = asyncio.Lock()
        self._active_run: asyncio.Task[InstanceResult] | None = None
        self._closing = False
        self.final_image_uuid: str | None = None
        self.retained_image_tag: str | None = None
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
        if self._lazy is None or self._closing:
            raise RuntimeError("ConTree environment is not running; call start() first.")
        return self._lazy

    async def start(self, force_build: bool) -> None:
        async with self._lock:
            if self._lazy is not None:
                raise RuntimeError("ConTree environment is already started.")
            if force_build and (self.environment_dir / DOCKERFILE_NAME).exists():
                raise ValueError("ConTree cannot force-build a Dockerfile; use the prebuilt docker_image.")
            self._closing = False
            self.final_image_uuid = None
            self.retained_image_tag = None
            try:
                await asyncio.wait_for(self._start(), timeout=self.task_env_config.build_timeout_sec)
            except BaseException:
                if self._lazy is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await await_cleanup(self._lazy.abort())
                self._lazy = None
                self._session = None
                await self._close_sandbox()
                raise

    async def _start(self) -> None:
        client = self._client
        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise RuntimeError("ConTree startup requires a prebuilt image.")
        # Resolve UUID/tag references without reimporting; OCI names use the V2
        # import helper and its cache. Neither path mutates the source image.
        if docker_image.startswith(("tag:", "uuid:")):
            image = docker_image.removeprefix("uuid:")
        else:
            try:
                from uuid import UUID

                UUID(docker_image)
                image = docker_image
            except ValueError:
                image = await self._import_image(client, docker_image)
        policy = (
            ManualSnapshotPolicy() if self._snapshot_idle_sec is None else IdleSnapshotPolicy(self._snapshot_idle_sec)
        )
        self._sandbox = create_async_sandbox_session(
            image=image,
            session_id=self.session_id,
            client=client,
            profile=self._profile if client is None else None,
            client_type=HttpxAsyncClient if client is None else None,
            session_kwargs={
                "vm_request": RunRequest(command="sleep", args=("2147483647",), timeout=self._vm_timeout),
                "snapshot_policy": policy,
                "snapshot_timeout": self._snapshot_timeout,
            },
        )
        self._lazy = await self._sandbox.__aenter__()  # noqa: PLC2801 - spans Harbor start/stop
        self._session = self._lazy.session
        self._client = self._session.client
        check = await self._execute('test "$(id -u)" = 0 && command -v bash && command -v sleep', cwd="/")
        self._check_result(check, "ConTree requires an image running as root with Bash and sleep")
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

    async def _close_sandbox(self) -> None:
        sandbox, self._sandbox = self._sandbox, None
        try:
            if sandbox is not None:
                await sandbox.__aexit__(None, None, None)
        finally:
            self._client = self._provided_client

    async def stop(self, delete: bool) -> None:
        self._closing = True
        if self._active_run is not None:
            self._active_run.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._active_run
        async with self._lock:
            lazy = self._lazy
            try:
                if lazy is not None:
                    if delete:
                        await self._discard_vm(lazy)
                    else:
                        await self._retain_image(lazy)
            finally:
                if lazy is not None and lazy.phase != "closed":
                    with suppress(Exception, asyncio.CancelledError):
                        await await_cleanup(lazy.abort())
                self._lazy = None
                self._session = None
                await self._close_sandbox()

    @staticmethod
    async def _discard_vm(lazy: AsyncLazySession) -> None:
        try:
            await lazy.abort()
        except APIConnectionError as error:
            if "Operation was cancelled, events dropped" not in str(error.__cause__):
                raise

    async def _retain_image(self, lazy: AsyncLazySession) -> None:
        await lazy.close(timeout=self._snapshot_timeout)
        if self._session is None or self._client is None:
            return
        image_uuid = self._session.image_uuid
        if image_uuid is None:
            raise RuntimeError("ConTree stop produced no image UUID")
        self.final_image_uuid = image_uuid
        tag = f"harbor-{uuid4().hex}"
        await self._client.update_image_tag(image_uuid, tag)
        self.retained_image_tag = tag
        self.logger.info("Retained ConTree image %s (tag %s)", image_uuid, tag)

    async def snapshot(self) -> str | None:
        """Save files and stop the current VM; the next command starts a new VM.

        Returns:
            The confirmed image UUID, or None before startup.

        """
        async with self._lock:
            lazy = self._require_lazy()
            await lazy.snapshot(timeout=self._snapshot_timeout)
            return self._session.image_uuid if self._session is not None else None

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        user = self._resolve_user(user)
        if user is not None and str(user) not in {"root", "0"}:
            raise ValueError(f"ConTree does not support switching users (requested {user!r}).")
        async with self._lock:
            return await self._execute(command, cwd=cwd, env=env, timeout_sec=timeout_sec, output_callback=True)

    async def _execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: float | None = None,
        output_callback: bool = False,
    ) -> ExecResult:
        result = await self._request(
            command, cwd=cwd, env=env, timeout_sec=timeout_sec, output_callback=output_callback
        )
        if not isinstance(result.state, InstanceResultState) or not isinstance(result.state.exit_code, int):
            raise TypeError("ConTree subprocess returned no exit code")
        return ExecResult(
            stdout=self._text(result.stdout), stderr=self._text(result.stderr), return_code=result.state.exit_code
        )

    @staticmethod
    def _text(stream: object) -> str:
        return stream.as_text() if isinstance(stream, StreamRepr) else ""

    async def _request(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: float | None = None,
        output_callback: bool = False,
    ) -> InstanceResult:
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
        )
        handle = None
        operation = None

        async def collect() -> InstanceResult:
            nonlocal handle, operation
            handle = await lazy.spawn_request(request)
            operation = lazy.operation
            if operation is None:
                raise RuntimeError("ConTree subprocess has no active operation")
            if output_callback:
                await self._stream_output(operation, handle.spid)
            result = await handle.wait()
            if not isinstance(result.state, InstanceResultState):
                raise TypeError("ConTree subprocess returned no exit state")
            for stream in (result.stdout, result.stderr):
                if isinstance(stream, StreamRepr) and stream.truncated is True:
                    self.logger.warning("ConTree command output was truncated at %s bytes per stream.", _OUTPUT_LIMIT)
            return result

        self._active_run = asyncio.create_task(collect())
        try:
            return await asyncio.wait_for(self._active_run, timeout=timeout)
        except BaseException:
            if handle is not None and operation is not None:
                current_handle, current_operation = handle, operation

                async def terminate() -> None:
                    try:
                        await self._terminate(lazy, current_operation, current_handle.spid)
                    except BaseException:
                        await lazy.abort()
                        raise

                with suppress(Exception, asyncio.CancelledError):
                    await await_cleanup(terminate())
            raise
        finally:
            self._active_run = None

    async def _stream_output(self, operation: AsyncOperationContract, spid: int) -> None:
        callback = self._output_callback()
        if callback is None:
            return
        decoders: dict[Literal["stdout", "stderr"], codecs.IncrementalDecoder] = {
            name: codecs.getincrementaldecoder("utf-8")("replace") for name in ("stdout", "stderr")
        }
        async for event in operation.events(spid=spid):
            if event.type == "stdout" and isinstance(event.data, EventDataStream):
                text = decoders["stdout"].decode(event.data.as_bytes())
                if text:
                    await callback(text, "stdout")
            elif event.type == "stderr" and isinstance(event.data, EventDataStream):
                text = decoders["stderr"].decode(event.data.as_bytes())
                if text:
                    await callback(text, "stderr")
            if event.type == "exit":
                break
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

        await asyncio.wait_for(kill_and_confirm(), timeout=self._terminate_timeout)

    @staticmethod
    def _check_result(result: ExecResult, action: str) -> None:
        if result.return_code:
            raise RuntimeError(f"{action} failed (exit {result.return_code}): {result.stderr or result.stdout}")

    @staticmethod
    def _remote_path(path: str) -> str:
        if not PurePosixPath(path).is_absolute() or "\0" in path:
            raise ValueError("ConTree file transfer paths must be absolute POSIX paths.")
        return path

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        target_path = self._remote_path(target_path)
        async with self._lock:
            await asyncio.wait_for(
                self._require_lazy().upload_file(source_path, target_path), timeout=_TRANSFER_TIMEOUT
            )

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        async with self._lock:
            await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        target_dir = self._remote_path(target_dir)
        await asyncio.wait_for(self._require_lazy().upload_dir(source_dir, target_dir), timeout=_TRANSFER_TIMEOUT)

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        source_path = self._remote_path(source_path)
        async with self._lock:
            await asyncio.wait_for(
                self._require_lazy().download_file(source_path, target_path), timeout=_TRANSFER_TIMEOUT
            )

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        source_dir = self._remote_path(source_dir)
        async with self._lock:
            await asyncio.wait_for(self._require_lazy().download_dir(source_dir, target_dir), timeout=_TRANSFER_TIMEOUT)
