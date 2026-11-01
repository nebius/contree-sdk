"""Harbor commands and file transfers in one long-running ConTree operation."""

from __future__ import annotations

import asyncio
import inspect
import io
import math
import tarfile
from collections.abc import AsyncIterator, Awaitable
from contextlib import aclosing, suppress
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import Literal

from contree_client import profiles
from contree_client.httpx import ContreeAsyncClient as HttpxAsyncClient
from contree_client.models import EventDataStream, InstanceResult, InstanceResultState, OperationStatus, StreamRepr
from contree_client.types import ContreeAsyncClient
from harbor.environments.base import BaseEnvironment, ExecResult, OutputCallback
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.environments.definition import COMPOSE_FILE_NAME, DOCKERFILE_NAME, should_upload_environment_dir
from harbor.models.trial.paths import EnvironmentPaths

from contree_sdk import async_import_image
from contree_sdk.file_io import write_download_async
from contree_sdk.files import AsyncClientFileTransfer, UploadFileSpec
from contree_sdk.session.contracts import AsyncSubprocessContract
from contree_sdk.session.operation_async import AsyncOperation


_OUTPUT_LIMIT = 10 * 1024 * 1024
_TRANSFER_TIMEOUT = 600
_KEEPALIVE_SLEEP_SECONDS = 2**31 - 1


async def extract_archive(chunks: AsyncIterator[bytes], target_dir: Path | str) -> None:
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as archive:
        async for chunk in chunks:
            await asyncio.to_thread(archive.write, chunk)
        await asyncio.to_thread(archive.seek, 0)
        with tarfile.open(fileobj=archive, mode="r:*") as tar:
            await asyncio.to_thread(tar.extractall, target_dir, filter="data")


async def _finish_cleanup(cleanup: Awaitable[object]) -> None:
    """Join cleanup even if Harbor cancels the caller again.

    Raises:
        asyncio.CancelledError: The caller was cancelled during cleanup.

    """
    task = asyncio.ensure_future(cleanup)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:  # noqa: PERF203 - consume each cancellation until cleanup completes
            cancelled = True
        except Exception:
            break
    if cancelled:
        with suppress(Exception, asyncio.CancelledError):
            task.result()
        raise asyncio.CancelledError
    task.result()


class ConTreeEnvironment(BaseEnvironment):
    """Harbor backend using one operation for the lifetime of a trial."""

    def __init__(
        self,
        *args,
        profile: str | None = None,
        operation_timeout: float = 1000,
        readiness_timeout: float = 120,
        snapshot_timeout: float = 120,
        terminate_timeout: float = 5,
        vm_timeout: float = 3600,
        client: ContreeAsyncClient | None = None,
        **kwargs,
    ) -> None:
        for name, value in (
            ("operation_timeout", operation_timeout),
            ("readiness_timeout", readiness_timeout),
            ("snapshot_timeout", snapshot_timeout),
            ("terminate_timeout", terminate_timeout),
            ("vm_timeout", vm_timeout),
        ):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be finite and positive")
        unknown = kwargs.keys() - inspect.signature(BaseEnvironment.__init__).parameters.keys()
        if unknown:
            raise TypeError(f"Unknown ConTree environment options: {', '.join(sorted(unknown))}")
        self._profile = profile
        self._operation_timeout = operation_timeout
        self._readiness_timeout = readiness_timeout
        self._snapshot_timeout = snapshot_timeout
        self._terminate_timeout = terminate_timeout
        self._vm_timeout = vm_timeout
        self._client = client
        self._provided_client = client
        self._operation: AsyncOperation | None = None
        self._transfer: AsyncClientFileTransfer | None = None
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

    def _require_operation(self) -> AsyncOperation:
        if self._operation is None or self._closing or self._operation.cancel_requested:
            raise RuntimeError("ConTree environment is not running; call start() first.")
        return self._operation

    async def start(self, force_build: bool) -> None:
        async with self._lock:
            if self._operation is not None:
                raise RuntimeError("ConTree environment is already started.")
            if force_build and (self.environment_dir / DOCKERFILE_NAME).exists():
                raise ValueError("ConTree cannot force-build a Dockerfile; use the prebuilt docker_image.")
            self._closing = False
            try:
                await self._start()
            except BaseException:
                try:
                    await _finish_cleanup(self._close_operation(save=False))
                except Exception:
                    self.logger.warning("ConTree startup cleanup failed.", exc_info=True)
                raise

    async def _start(self) -> None:
        if self._provided_client is None:
            profile = (
                profiles.resolve_profile(self._profile)
                if self._profile
                else profiles.from_env() or profiles.resolve_profile()
            )
            self._client = HttpxAsyncClient.from_profile(profile)
            await self._client.open()
        client = self._client
        if client is None:
            raise RuntimeError("ConTree client is not available")

        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise RuntimeError("ConTree startup requires a prebuilt image.")
        contree_image = await self._import_image(client, docker_image)

        response = await client.spawn_instance(
            "sleep",
            contree_image,
            args=[str(_KEEPALIVE_SLEEP_SECONDS)],
            disposable=False,
            timeout=math.ceil(self._vm_timeout),
        )
        if not isinstance(response.uuid, str):
            raise TypeError("ConTree operation response has no UUID")
        self._operation = AsyncOperation(client, response.uuid, shutdown_timeout=self._snapshot_timeout)
        await self._operation.__aenter__()  # noqa: PLC2801 - spans Harbor start/stop
        await self._operation.wait_ready(timeout=self._readiness_timeout)
        self._transfer = AsyncClientFileTransfer(client)

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

    async def _import_image(self, client: ContreeAsyncClient, source: str) -> str:
        return await async_import_image(
            source,
            timeout=math.ceil(self.task_env_config.build_timeout_sec),
            client=client,
        )

    async def _close_operation(self, *, save: bool) -> None:
        operation, self._operation = self._operation, None
        try:
            if operation is not None:
                try:
                    if save and not operation.cancel_requested:
                        await self._save_operation(operation)
                    elif not operation.cancel_requested:
                        await operation.cancel()
                except BaseException:
                    with suppress(Exception, asyncio.CancelledError):
                        await operation.cancel()
                    raise
                finally:
                    await operation.shutdown()
        finally:
            self._transfer = None
            try:
                if self._provided_client is None and self._client is not None:
                    await self._client.close()
            finally:
                self._client = self._provided_client

    async def _save_operation(self, operation: AsyncOperation) -> None:
        await operation.signal("SIGTERM")
        await operation.wait(timeout=self._snapshot_timeout)
        response = operation.final_response
        if (
            response is None
            or response.status != OperationStatus.SUCCESS
            or not isinstance(response.result_image_uuid, str)
        ):
            raise RuntimeError("ConTree operation did not save its final image")

    async def stop(self, delete: bool = True) -> None:
        """Save the operation's final image and release resources."""
        self._closing = True
        if self._active_run is not None:
            self._active_run.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await _finish_cleanup(self._active_run)
        async with self._lock:
            await _finish_cleanup(self._close_operation(save=True))

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
        timeout = self._operation_timeout if timeout_sec is None else timeout_sec
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Command timeout must be finite and positive.")
        operation = self._require_operation()

        async def run_command() -> InstanceResult:
            handle = await self._spawn_subprocess(
                operation,
                command,
                cwd=cwd,
                env=env,
                uid=uid,
                gid=gid,
            )

            async def consume() -> InstanceResult:
                async for event in handle:
                    if (
                        output_callback is not None
                        and event.type in {"stdout", "stderr"}
                        and isinstance(event.data, EventDataStream)
                    ) and (chunk := event.data.as_text()):
                        stream: Literal["stdout", "stderr"] = "stdout" if event.type == "stdout" else "stderr"
                        await output_callback(chunk, stream)
                return await handle.wait()

            try:
                return await asyncio.wait_for(consume(), timeout=timeout)
            except BaseException:
                with suppress(Exception):
                    await _finish_cleanup(self._kill_subprocess(operation, handle))
                raise

        self._active_run = asyncio.create_task(run_command())
        try:
            result = await self._active_run
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

    async def _spawn_subprocess(
        self,
        operation: AsyncOperation,
        command: str,
        *,
        cwd: str | None,
        env: dict[str, str] | None,
        uid: int | None,
        gid: int | None,
    ) -> AsyncSubprocessContract:
        return await operation.run(
            "/bin/bash",
            args=("-c", command),
            env=self._merge_env(env),
            cwd=cwd if cwd is not None else self.task_env_config.workdir,
            uid=uid,
            gid=gid,
            truncate_output_at=_OUTPUT_LIMIT,
        )

    async def _kill_subprocess(self, operation: AsyncOperation, handle: AsyncSubprocessContract) -> None:
        try:
            await operation.signal("SIGKILL", spid=handle.spid)
            await handle.wait(timeout=self._terminate_timeout)
        except BaseException:
            await operation.cancel()
            raise

    @staticmethod
    def _check_result(result: ExecResult, action: str) -> None:
        if result.return_code:
            raise RuntimeError(f"{action} failed (exit {result.return_code}): {result.stderr or result.stdout}")

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        async with self._lock:
            self._remote_path(target_path)
            await asyncio.wait_for(self._apply_file(source_path, target_path), timeout=_TRANSFER_TIMEOUT)

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        async with self._lock:
            await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        self._remote_path(target_dir)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            tar.add(source_dir, arcname=".")
        await asyncio.wait_for(self._apply_file(archive.getvalue(), target_dir, unpack=True), timeout=_TRANSFER_TIMEOUT)

    async def _apply_file(self, source: Path | str | bytes, target: str, *, unpack: bool = False) -> None:
        operation = self._require_operation()
        if self._transfer is None:
            raise RuntimeError("ConTree file transfer is not available")
        spec = await self._transfer.upload(UploadFileSpec(source=source, path=target))
        if not isinstance(spec.uuid, str):
            raise TypeError("ConTree file upload returned no UUID")
        await operation.client.apply_instance_file(
            operation.uuid, spec.uuid, target, unpack=unpack, replace=True, merge=True
        )

    @staticmethod
    def _remote_path(path: str) -> PurePosixPath:
        destination = PurePosixPath(path)
        if not destination.is_absolute() or "\0" in path:
            raise ValueError("file paths must be absolute and contain no NUL characters")
        return destination

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        async with self._lock:
            self._remote_path(source_path)
            operation = self._require_operation()
            async with aclosing(
                operation.client.inspect_instance_download_stream(operation.uuid, source_path)
            ) as chunks:
                await asyncio.wait_for(
                    write_download_async(chunks, target_path, path=source_path), timeout=_TRANSFER_TIMEOUT
                )

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        async with self._lock:
            self._remote_path(source_dir)
            operation = self._require_operation()
            async with aclosing(operation.client.inspect_instance_archive(operation.uuid, source_dir)) as chunks:
                await asyncio.wait_for(extract_archive(chunks, target_dir), timeout=_TRANSFER_TIMEOUT)
