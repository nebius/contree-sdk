"""Apply uploaded stage archives in one VM and commit the completed COPY layer."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass

from contree_client.models import EventDataStream

from contree_sdk.exceptions import DockerBuildError
from contree_sdk.execution import RunRequest
from contree_sdk.session.cleanup import await_cleanup

from .context import AsyncBuildContext, BuildContext
from .kw_run import check_success, require_session, require_session_async


@dataclass(frozen=True)
class UploadedArchive:
    file_uuid: str
    path: str


def copy_request(ctx: BuildContext | AsyncBuildContext) -> RunRequest:
    return RunRequest(
        command="sleep",
        args=("infinity",),
        files=ctx.pending_files_payload() if ctx.pending else None,
        disposable=False,
        uid=0,
        gid=0,
        hostname="linuxkit",
        timeout=ctx.timeout or None,
    )


def remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("COPY --from exceeded its operation timeout")
    return seconds


def apply_copy_layer(ctx: BuildContext, archive: UploadedArchive, commands: list[str], *, branch: str) -> None:
    session = require_session(ctx.session)
    request = copy_request(ctx)
    deadline = time.monotonic() + ctx.timeout if ctx.timeout else None
    with session.spawn_request(request) as operation:
        try:  # noqa: PLW0717 - cancel the whole COPY operation on any preparation or transfer failure
            if ctx.progress.current is not None:
                ctx.progress.current.operation_uuid = operation.uuid
            ctx.emit_event("operation_started")
            for event in operation.events(timeout=remaining(deadline)):
                if event.type == "spawn" and event.spid == 1:
                    break
            else:
                raise DockerBuildError("COPY --from VM stopped before startup")  # noqa: TRY301 - shared cleanup boundary
            remaining(deadline)
            ctx.client.apply_instance_file(
                operation.uuid, archive.file_uuid, archive.path, unpack=True, replace=True, merge=True
            )
            for command in commands:
                process = operation.run(command, shell=True, uid=0, gid=0)
                for event in operation.events(spid=process.spid, timeout=remaining(deadline)):
                    if event.type in {"stdout", "stderr"} and isinstance(event.data, EventDataStream):
                        ctx.emit_event("stdout" if event.type == "stdout" else "stderr", data=event.data.as_bytes())
                    if event.type == "exit":
                        break
                result = process.wait(timeout=remaining(deadline))
                if ctx.progress.current is not None:
                    ctx.progress.current.result = result
                check_success(result, (command,), True)
            operation.signal("SIGTERM", spid=1)
            operation.wait(timeout=remaining(deadline))
        except BaseException:
            with suppress(Exception):
                operation.cancel()
            raise
    entry = session.commit_result(
        operation, title="COPY --from", data={"docker_hash": branch, "docker_copy_complete": True}
    )
    if entry is None:
        raise DockerBuildError("COPY --from result was not saved by the session")


async def apply_copy_layer_async(
    ctx: AsyncBuildContext, archive: UploadedArchive, commands: list[str], *, branch: str
) -> None:
    session = require_session_async(ctx.session)
    request = copy_request(ctx)
    deadline = time.monotonic() + ctx.timeout if ctx.timeout else None
    async with await session.spawn_request(request) as operation:
        try:  # noqa: PLW0717 - cancel the whole COPY operation on any preparation or transfer failure
            if ctx.progress.current is not None:
                ctx.progress.current.operation_uuid = operation.uuid
            await ctx.emit_event("operation_started")
            async for event in operation.events(timeout=remaining(deadline)):
                if event.type == "spawn" and event.spid == 1:
                    break
            else:
                raise DockerBuildError("COPY --from VM stopped before startup")  # noqa: TRY301 - shared cleanup boundary
            await asyncio.wait_for(
                ctx.client.apply_instance_file(
                    operation.uuid, archive.file_uuid, archive.path, unpack=True, replace=True, merge=True
                ),
                timeout=remaining(deadline),
            )
            for command in commands:
                process = await operation.run(command, shell=True, uid=0, gid=0)
                async for event in operation.events(spid=process.spid, timeout=remaining(deadline)):
                    if event.type in {"stdout", "stderr"} and isinstance(event.data, EventDataStream):
                        await ctx.emit_event(
                            "stdout" if event.type == "stdout" else "stderr", data=event.data.as_bytes()
                        )
                    if event.type == "exit":
                        break
                result = await process.wait(timeout=remaining(deadline))
                if ctx.progress.current is not None:
                    ctx.progress.current.result = result
                check_success(result, (command,), True)
            await operation.signal("SIGTERM", spid=1)
            await operation.wait(timeout=remaining(deadline))
        except BaseException:
            with suppress(Exception, asyncio.CancelledError):
                await await_cleanup(operation.cancel())
            raise
    entry = await session.commit_result(
        operation, title="COPY --from", data={"docker_hash": branch, "docker_copy_complete": True}
    )
    if entry is None:
        raise DockerBuildError("COPY --from result was not saved by the session")
