"""Build a Dockerfile against a ConTree client (async)."""

from __future__ import annotations

import inspect
import time
from asyncio import to_thread
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from pathlib import Path

from contree_client.types import ContreeAsyncClient

from contree_sdk.cache import AsyncCache, AsyncMemoryCache
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.store import AsyncMemoryStore, AsyncStore

from .context import BUILD_TIMEOUT_DEFAULT, AsyncBuildContext, BuildRequest, BuildStepEvent, resolve_build_paths
from .events import BuildEvent
from .keyword import DockerKeyword
from .kw_run import RunKeyword
from .local_context import LocalContext
from .parser import DockerfileParser, make_session_key, validate_first_directive
from .url_fetch import AsyncFetchResponse
from .url_fetch import http_fetch_async as default_http_fetch_async


class ContreeAsyncDockerBuilder:
    """Build a Dockerfile from `context`.

    Applies each directive against a content-addressed layer cache keyed by
    the build's session.
    """

    context_class: type[AsyncBuildContext] = AsyncBuildContext

    def __init__(
        self,
        client: ContreeAsyncClient,
        *,
        store: AsyncStore | None = None,
        cache: AsyncCache | None = None,
        http_fetch_async: Callable[[str, str, Iterable[tuple[str, str]]], Awaitable[AsyncFetchResponse]] | None = None,
        parser: DockerfileParser | None = None,
        session_factory: Callable[..., ContreeAsyncSession] | None = None,
    ) -> None:
        self.client = client
        self.store = store if store is not None else AsyncMemoryStore()
        self.cache = cache if cache is not None else AsyncMemoryCache()
        self.http_fetch_async = http_fetch_async or default_http_fetch_async
        self.parser = parser if parser is not None else DockerfileParser()
        self.session_factory = session_factory if session_factory is not None else ContreeAsyncSession
        self.ctx: AsyncBuildContext | None = None

    @property
    def session(self) -> ContreeAsyncSession | None:
        return self.ctx.session if self.ctx is not None else None

    async def build(
        self,
        context: str | Path,
        *,
        dockerfile: str | Path | None = None,
        tag: str | None = None,
        build_args: dict[str, str] | None = None,
        no_cache: bool = False,
        timeout: int = BUILD_TIMEOUT_DEFAULT,
        session_id: str | None = None,
        on_event: Callable[[BuildEvent], object] | None = None,
        on_step: Callable[[BuildStepEvent], object] | None = None,
    ) -> str:
        context_dir, dockerfile_path = await to_thread(resolve_build_paths, context, dockerfile)

        try:
            directives = self.parse(await to_thread(dockerfile_path.read_text))
        except ValueError as exc:
            raise ValueError(f"Dockerfile parse error: {exc}") from exc

        if not validate_first_directive(directives):
            raise ValueError("Dockerfile must contain a FROM directive")

        ctx = await self.create_context(
            BuildRequest(
                context_dir=context_dir,
                dockerfile_path=dockerfile_path,
                session_id=session_id or make_session_key(context_dir),
                build_args=dict(build_args or {}),
                no_cache=no_cache,
                timeout=timeout,
            )
        )
        self.ctx = ctx
        ctx.on_event = on_event

        for index, directive in enumerate(directives):
            image_before = ctx.last_image or None
            ctx.last_cache_hit = False
            start = time.monotonic()
            try:
                await self.run_step(directive, ctx, index=index)
            except BaseException as exc:
                with suppress(BaseException):
                    await emit_step(
                        on_step,
                        BuildStepEvent(
                            index, repr(directive), False, image_before, None, time.monotonic() - start, exc
                        ),
                    )
                raise
            await emit_step(
                on_step,
                BuildStepEvent(
                    index,
                    repr(directive),
                    ctx.last_cache_hit,
                    image_before,
                    ctx.last_image or None,
                    time.monotonic() - start,
                    None,
                ),
            )
        await self.finalize(ctx)

        if not ctx.last_image:
            raise DockerBuildError("build produced no image")

        if tag:
            await self.client.update_image_tag(ctx.last_image, tag)

        return ctx.last_image

    def parse(self, text: str) -> list[DockerKeyword]:
        """Return build directives through the configured parser.

        Returns:
            The parsed directives in source order.

        """
        return self.parser.parse(text)

    async def create_context(self, request: BuildRequest) -> AsyncBuildContext:
        """Construct per-build state using the public context and session factories.

        Returns:
            A context owned by this build invocation.

        """
        return self.context_class(
            client=self.client,
            store=self.store,
            cache=self.cache,
            local=await to_thread(LocalContext.from_dir, request.context_dir),
            http_fetch_async=self.http_fetch_async,
            session_factory=self.session_factory,
            directive_executor=self.run_step,
            session_id=request.session_id,
            build_args=dict(request.build_args),
            no_cache=request.no_cache,
            timeout=request.timeout,
        )

    async def run_step(self, directive: DockerKeyword, context: AsyncBuildContext, *, index: int | None = None) -> None:
        """Report one directive execution, including nested and synthetic steps."""
        parent = context.progress.current
        parent_cache_hit = context.last_cache_hit
        context.progress.start(repr(directive), index, context.last_image or None)
        context.last_cache_hit = False
        try:
            await context.emit_event("step_started")
            await self.execute_directive(directive, context)
            if context.last_cache_hit:
                await context.emit_event("cache_hit")
            await context.emit_event("step_completed")
        except BaseException as error:
            with suppress(BaseException):
                await context.emit_event("step_failed", error=error)
            raise
        finally:
            context.progress.current = parent
            if parent is not None:
                context.last_cache_hit = parent_cache_hit

    async def execute_directive(self, directive: DockerKeyword, context: AsyncBuildContext) -> None:  # noqa: PLR6301 - public extension contract
        """Execute one directive. Override for policy checks or instrumentation."""
        await directive.execute_async(context)

    async def finalize(self, context: AsyncBuildContext) -> None:
        """Commit pending file attachments through the same directive execution hook."""
        if context.pending:
            await self.run_step(RunKeyword(parts=(":",), shell_form=True), context)


async def emit_step(on_step: Callable[[BuildStepEvent], object] | None, event: BuildStepEvent) -> None:
    if on_step is None:
        return
    result = on_step(event)
    if inspect.isawaitable(result):
        await result
