"""`RUN ...` - execute a command and capture the resulting image."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import ClassVar

from contree_client.models import InstanceResult

from contree_sdk.exceptions import DockerBuildError
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.base import exit_code_of, or_none
from contree_sdk.session.sync import ContreeSession

from .context import AsyncBuildContext, BuildContext
from .keyword import DockerKeyword, parse_command_form


DISPLAY_TITLE_MAX_LEN = 200


@dataclass(frozen=True, repr=False)
class RunKeyword(DockerKeyword):
    NAME: ClassVar[str] = "RUN"
    parts: tuple[str, ...] = field(default_factory=tuple)
    shell_form: bool = True

    def __repr__(self) -> str:
        if self.shell_form:
            return f"RUN {self.parts[0] if self.parts else ''}"
        return f"RUN {json.dumps(list(self.parts))}"

    @classmethod
    def parse(cls, args_text: str) -> RunKeyword:
        raw = args_text.strip()
        if not raw:
            raise ValueError("RUN requires a command")
        parts, shell_form = parse_command_form(raw)
        return cls(parts=tuple(parts), shell_form=shell_form)

    def serialize(self) -> str:
        if self.shell_form:
            return f"RUN {self.parts[0]}"
        return f"RUN {json.dumps(list(self.parts))}"

    def execute(self, ctx: BuildContext) -> None:
        sub_parts = tuple(ctx.substitute(part) for part in self.parts)
        contribution = f"RUN shell={self.shell_form} parts={json.dumps(list(sub_parts))}"
        chain = ctx.chain(contribution)
        branch_name = f"layer:{ctx.short_hash(chain)}"

        if ctx.try_cache_hit(branch_name) is not None:
            ctx.parent_hash = chain
            ctx.pending.clear()
            return

        session = require_session(ctx.session)
        command, args, shell = build_command(sub_parts, self.shell_form, ctx.user)
        cwd = ctx.workdir if ctx.workdir != "/" else None
        files = ctx.pending_files_payload() if ctx.pending else None
        timeout = ctx.timeout if ctx.timeout else None
        if shell:
            result = session.run(
                shell=command,
                args=args,
                env=ctx.env or None,
                cwd=cwd,
                files=files,
                disposable=False,
                branch=branch_name,
                hostname="linuxkit",
                truncate_output_at=65536,
                timeout=timeout,
            )
        else:
            result = session.run(
                command,
                args=args,
                env=ctx.env or None,
                cwd=cwd,
                files=files,
                disposable=False,
                branch=branch_name,
                hostname="linuxkit",
                truncate_output_at=65536,
                timeout=timeout,
            )
        check_success(result, sub_parts, self.shell_form)

        ctx.parent_hash = chain
        ctx.pending.clear()

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        sub_parts = tuple(ctx.substitute(part) for part in self.parts)
        contribution = f"RUN shell={self.shell_form} parts={json.dumps(list(sub_parts))}"
        chain = ctx.chain(contribution)
        branch_name = f"layer:{ctx.short_hash(chain)}"

        if await ctx.try_cache_hit(branch_name) is not None:
            ctx.parent_hash = chain
            ctx.pending.clear()
            return

        session = require_session_async(ctx.session)
        command, args, shell = build_command(sub_parts, self.shell_form, ctx.user)
        cwd = ctx.workdir if ctx.workdir != "/" else None
        files = ctx.pending_files_payload() if ctx.pending else None
        timeout = ctx.timeout if ctx.timeout else None
        if shell:
            result = await session.run(
                shell=command,
                args=args,
                env=ctx.env or None,
                cwd=cwd,
                files=files,
                disposable=False,
                branch=branch_name,
                hostname="linuxkit",
                truncate_output_at=65536,
                timeout=timeout,
            )
        else:
            result = await session.run(
                command,
                args=args,
                env=ctx.env or None,
                cwd=cwd,
                files=files,
                disposable=False,
                branch=branch_name,
                hostname="linuxkit",
                truncate_output_at=65536,
                timeout=timeout,
            )
        check_success(result, sub_parts, self.shell_form)

        ctx.parent_hash = chain
        ctx.pending.clear()


def check_success(result: InstanceResult, parts: tuple[str, ...], shell_form: bool) -> None:
    exit_code = exit_code_of(result)
    if exit_code is not None and exit_code != 0:
        title = display_title(parts, shell_form)
        stdout = or_none(result.stdout)
        stderr = or_none(result.stderr)
        raise DockerBuildError(
            f"RUN {title!r} exited with code {exit_code}\n"
            f"stdout: {stdout.as_text() if stdout is not None else ''}\n"
            f"stderr: {stderr.as_text() if stderr is not None else ''}"
        )


def require_session(session: ContreeSession | None) -> ContreeSession:
    if session is None:
        raise DockerBuildError("no active FROM: cannot RUN without a base image")
    return session


def require_session_async(session: ContreeAsyncSession | None) -> ContreeAsyncSession:
    if session is None:
        raise DockerBuildError("no active FROM: cannot RUN without a base image")
    return session


def build_command(parts: tuple[str, ...], shell_form: bool, user: str) -> tuple[str, list[str], bool]:
    # maps parsed RUN parts plus an optional active USER into a (command, args, shell) triple
    if shell_form:
        expr = parts[0]
        if user:
            return wrap_with_user(expr, user), [], True
        return expr, [], True

    command = parts[0]
    args = list(parts[1:])
    if user:
        joined = shlex.join([command, *args])
        return wrap_with_user(joined, user), [], True
    return command, args, False


def wrap_with_user(expr: str, user: str) -> str:
    return f"su -s /bin/sh -c {shlex.quote(expr)} {shlex.quote(user)}"


def display_title(parts: tuple[str, ...], shell_form: bool) -> str:
    if shell_form:
        return f"RUN {parts[0]}"[:DISPLAY_TITLE_MAX_LEN]
    return f"RUN {json.dumps(list(parts))}"[:DISPLAY_TITLE_MAX_LEN]
