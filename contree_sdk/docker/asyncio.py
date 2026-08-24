"""Build a Dockerfile against a ConTree client (async)."""

from __future__ import annotations

import inspect
import time
from asyncio import to_thread
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from contree_client.types import ContreeAsyncClient

from contree_sdk.cache import AsyncCache, AsyncMemoryCache
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.store import AsyncMemoryStore, AsyncStore

from .context import BUILD_TIMEOUT_DEFAULT, AsyncBuildContext, BuildStepEvent, resolve_build_paths
from .kw_run import RunKeyword
from .local_context import LocalContext
from .parser import make_session_key, parse_dockerfile, validate_first_directive
from .url_fetch import AsyncFetchResponse
from .url_fetch import http_fetch_async as default_http_fetch_async


class ContreeAsyncDockerBuilder:
    """Build a Dockerfile from `context`.

    Applies each directive against a content-addressed layer cache keyed by
    the build's session.
    """

    def __init__(
        self,
        client: ContreeAsyncClient,
        *,
        store: AsyncStore | None = None,
        cache: AsyncCache | None = None,
        http_fetch_async: Callable[[str, str, Iterable[tuple[str, str]]], Awaitable[AsyncFetchResponse]] | None = None,
    ) -> None:
        self.client = client
        self.store = store or AsyncMemoryStore()
        self.cache = cache or AsyncMemoryCache()
        self.http_fetch_async = http_fetch_async or default_http_fetch_async
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
        on_step: Callable[[BuildStepEvent], object] | None = None,
    ) -> str:
        context_dir, dockerfile_path = await to_thread(resolve_build_paths, context, dockerfile)

        try:
            directives = parse_dockerfile(await to_thread(dockerfile_path.read_text))
        except ValueError as exc:
            raise ValueError(f"Dockerfile parse error: {exc}") from exc

        if not validate_first_directive(directives):
            raise ValueError("Dockerfile must contain a FROM directive")

        ctx = AsyncBuildContext(
            client=self.client,
            store=self.store,
            cache=self.cache,
            local=await to_thread(LocalContext.from_dir, context_dir),
            http_fetch_async=self.http_fetch_async,
            session_id=session_id or make_session_key(context_dir),
            build_args=dict(build_args or {}),
            no_cache=no_cache,
            timeout=timeout,
        )
        self.ctx = ctx

        for index, directive in enumerate(directives):
            image_before = ctx.last_image or None
            ctx.last_cache_hit = False
            start = time.monotonic()
            try:
                await directive.execute_async(ctx)
            except BaseException as exc:
                await emit_step(
                    on_step,
                    BuildStepEvent(index, repr(directive), False, image_before, None, time.monotonic() - start, exc),
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
        await finalize_pending(ctx)

        if not ctx.last_image:
            raise DockerBuildError("build produced no image")

        if tag:
            await self.client.update_image_tag(ctx.last_image, tag)

        return ctx.last_image


async def emit_step(on_step: Callable[[BuildStepEvent], object] | None, event: BuildStepEvent) -> None:
    if on_step is None:
        return
    result = on_step(event)
    if inspect.isawaitable(result):
        await result


async def finalize_pending(ctx: AsyncBuildContext) -> None:
    """If COPY/ADD left files pending, commit them via a trivial RUN."""
    if not ctx.pending:
        return
    await RunKeyword(parts=(":",), shell_form=True).execute_async(ctx)
