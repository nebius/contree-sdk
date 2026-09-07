from __future__ import annotations

import asyncio
import codecs
import inspect
import math
import shlex
import stat
from collections.abc import AsyncGenerator
from contextlib import aclosing, suppress
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, cast
from uuid import UUID, uuid4

from contree_client.httpx import ContreeAsyncClient
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.environments.definition import COMPOSE_FILE_NAME, DOCKERFILE_NAME, should_upload_environment_dir
from harbor.environments.tar_transfer import extract_dir_from_file, pack_dir_to_file, remote_unpack_command
from harbor.models.trial.config import ResourceMode
from harbor.models.trial.paths import EnvironmentPaths

from contree_sdk import Contree
from contree_sdk.sdk.exceptions import OperationTimedOutError
from contree_sdk.sdk.objects.image import ContreeImage
from contree_sdk.sdk.objects.image_like.waiter_common import OutputChunk, StreamName
from contree_sdk.sdk.objects.session import ContreeSession
from contree_sdk.utils.models.file import UploadFileSpec


_OUTPUT_LIMIT = 10 * 1024 * 1024
_TRANSFER_TIMEOUT = 600


class ConTreeEnvironment(BaseEnvironment):
    """Harbor environment using a sequence of ConTree filesystem snapshots.

    Commands share files, but do not share processes or in-memory state.
    Configure authentication with a saved ConTree profile. ``profile`` and
    ``operation_timeout`` may be passed using Harbor's ``--ek`` option.
    An injected ``client`` is supported for Python callers and remains owned
    by the caller. Clients created from a profile are closed by this adapter.
    """

    def __init__(
        self,
        *args,
        profile: str | None = None,
        operation_timeout: float = 1000,
        client: Contree | None = None,
        **kwargs,
    ) -> None:
        if not math.isfinite(operation_timeout) or operation_timeout <= 0:
            raise ValueError("operation_timeout must be finite and positive")
        unknown = kwargs.keys() - inspect.signature(BaseEnvironment.__init__).parameters.keys()
        if unknown:
            raise TypeError(f"Unknown ConTree environment options: {', '.join(sorted(unknown))}")
        self._profile = profile
        self._operation_timeout = operation_timeout
        self._client = client
        self._owns_client = client is None
        self._session: ContreeSession | None = None
        self._lock = asyncio.Lock()
        self._active_run: asyncio.Task[ExecResult] | None = None
        self._closing = False
        self.final_image_uuid: UUID | None = None
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
        for resource, value in (("cpu", config.cpus), ("memory", config.memory_mb)):
            if value is not None and self._resource_mode(resource) == ResourceMode.AUTO:
                self.logger.warning("ConTree cannot enforce %s resources; the configured value is ignored.", resource)
        if config.storage_mb is not None:
            self.logger.warning(
                "ConTree cannot enforce storage resources; storage_mb=%s (including override_storage_mb) is ignored.",
                config.storage_mb,
            )

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

    def _require_session(self) -> ContreeSession:
        if self._session is None or self._closing:
            raise RuntimeError("ConTree environment is not running; call start() first.")
        return self._session

    async def start(self, force_build: bool) -> None:
        async with self._lock:
            if self._session is not None:
                raise RuntimeError("ConTree environment is already started.")
            if force_build and (self.environment_dir / DOCKERFILE_NAME).exists():
                raise ValueError("ConTree cannot force-build a Dockerfile; use the prebuilt docker_image.")
            self._closing = False
            self.final_image_uuid = None
            self.retained_image_tag = None
            try:
                if self._client is None:
                    self._client = Contree(
                        ContreeAsyncClient.from_profile(self._profile),
                        operation_timeout=self._operation_timeout,
                    )
                await asyncio.wait_for(self._start(self._client), timeout=self.task_env_config.build_timeout_sec)
            except BaseException:
                self._session = None
                await self._close_client()
                raise

    async def _start(self, client: Contree) -> None:
        docker_image = self.task_env_config.docker_image
        if docker_image is None:
            raise ValueError("ConTree requires a prebuilt docker_image.")
        image = await client.images.pull_image_by_oci(docker_image, timeout=self.task_env_config.build_timeout_sec)
        self._session = image.session()
        # The SDK has no user override. Verify root explicitly, including
        # Bash/tar prerequisites, before accepting work.
        check = await self._execute('test "$(id -u)" = 0 && command -v bash && command -v tar', cwd="/")
        self._check_result(check, "ConTree requires an image running as root with Bash and tar")
        paths = EnvironmentPaths()
        dirs = [str(paths.agent_dir), str(paths.verifier_dir), str(paths.artifacts_dir)]
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

    async def _close_client(self) -> None:
        if self._owns_client and self._client is not None:
            client, self._client = self._client, None
            await client.api.close()

    async def stop(self, delete: bool) -> None:
        self._closing = True
        if self._active_run is not None:
            self._active_run.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._active_run
        async with self._lock:
            try:
                if self._session is not None:
                    self.final_image_uuid = self._session.uuid
                    if not delete:
                        tag = f"harbor-{uuid4().hex}"
                        await self._session.tag_as(tag)
                        self.retained_image_tag = tag
                        self.logger.info("Retained ConTree image %s (tag %s)", self.final_image_uuid, tag)
                    # Untagged snapshots are managed by the service. Never
                    # remove the source image's tag or imply physical deletion.
            finally:
                self._session = None
                await self._close_client()

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
            return await self._execute(command, cwd=cwd, env=env, timeout_sec=timeout_sec)

    async def _execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: float | None = None,
        files: list[str | Path | UploadFileSpec] | None = None,
    ) -> ExecResult:
        session = self._require_session()
        timeout = self._operation_timeout if timeout_sec is None else timeout_sec
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Command timeout must be finite and positive.")
        previous_uuid = session.uuid
        run = session.run(
            shell=command,
            env={**(self._merge_env(env) or {}), "SHELL": "/bin/bash"},
            cwd=cwd if cwd is not None else self.task_env_config.workdir,
            timeout=timeout,
            files=files,
            disposable=False,
            preserve_env=False,
            stdout=bytes,
            stderr=bytes,
            truncate_output_at=_OUTPUT_LIMIT,
        )
        self._active_run = asyncio.create_task(self._collect_run(run))
        try:
            return await self._active_run
        except BaseException as exc:
            # A cancelled/failed operation has no committed snapshot. Restore
            # the last completed image so Harbor can still collect its logs.
            self._session = ContreeImage(session.client, previous_uuid, None).session()
            self.logger.warning("ConTree operation failed; retaining the last completed filesystem snapshot.")
            if isinstance(exc, OperationTimedOutError):
                raise TimeoutError("ConTree command exceeded its timeout.") from exc
            raise
        finally:
            self._active_run = None

    async def _collect_run(self, run: ContreeSession) -> ExecResult:
        callback = self._output_callback()
        if callback is None:
            await run
        else:
            decoders: dict[StreamName, codecs.IncrementalDecoder] = {
                name: codecs.getincrementaldecoder("utf-8")("replace") for name in ("stdout", "stderr")
            }
            async with aclosing(cast("AsyncGenerator[OutputChunk, None]", run.iter_output())) as chunks:
                async for chunk in chunks:
                    text = decoders[chunk.stream_name].decode(chunk.value)
                    if text:
                        await callback(text, chunk.stream_name)
            for name, decoder in decoders.items():
                if tail := decoder.decode(b"", final=True):
                    await callback(tail, name)
        result = run.result
        if result.truncated:
            self.logger.warning("ConTree command output was truncated at %s bytes per stream.", _OUTPUT_LIMIT)
        return ExecResult(
            stdout=self._decode_output(result.stdout),
            stderr=self._decode_output(result.stderr),
            return_code=result.exit_code,
        )

    @staticmethod
    def _decode_output(output: Any) -> str:
        return output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output or "")

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
        source = Path(source_path)
        mode = stat.S_IMODE((await asyncio.to_thread(source.stat)).st_mode)
        async with self._lock:
            result = await self._execute(
                "true", cwd="/", files=[UploadFileSpec(source=source, path=target_path, mode=mode)]
            )
            self._check_result(result, "Uploading file")

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        async with self._lock:
            await self._upload_dir(source_dir, target_dir)

    async def _upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        target_dir = self._remote_path(target_dir)
        archive = f"/tmp/.harbor-{uuid4().hex}.tar.gz"  # noqa: S108 -- unique path in the remote trial image
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "upload.tar.gz"
            await asyncio.to_thread(pack_dir_to_file, source_dir, source)
            command = (
                f'{remote_unpack_command(archive, target_dir)}; status=$?; rm -f {shlex.quote(archive)}; exit "$status"'
            )
            result = await self._execute(
                command,
                cwd="/",
                timeout_sec=_TRANSFER_TIMEOUT,
                files=[UploadFileSpec(source=source, path=archive)],
            )
            self._check_result(result, "Uploading directory")

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        source_path = self._remote_path(source_path)
        async with self._lock:
            session = self._require_session()
            target = Path(target_path)
            await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
            await session.download(source_path, target)

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        source_dir = self._remote_path(source_dir)
        async with self._lock:
            session = self._require_session()
            with TemporaryDirectory() as tmp:
                archive = Path(tmp) / "download.tar"
                stream = session.client.api.inspect_image_archive(await session.image_uuid(), source_dir)
                with archive.open("wb") as output:
                    async with aclosing(stream):
                        async for chunk in stream:
                            await asyncio.to_thread(output.write, chunk)
                await asyncio.to_thread(extract_dir_from_file, archive, target_dir)
