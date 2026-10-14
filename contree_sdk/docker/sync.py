"""Build a Dockerfile against a ConTree client (sync)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from pathlib import Path

from contree_client.types import ContreeSyncClient

from contree_sdk.cache import SyncCache, SyncMemoryCache
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.session.sync import ContreeSession
from contree_sdk.store import SyncMemoryStore, SyncStore

from .context import BUILD_TIMEOUT_DEFAULT, BuildContext, BuildRequest, BuildStepEvent, resolve_build_paths
from .events import BuildEvent
from .keyword import DockerKeyword
from .kw_run import RunKeyword
from .local_context import LocalContext
from .parser import DockerfileParser, make_session_key, validate_first_directive
from .url_fetch import FetchResponse
from .url_fetch import http_fetch as default_http_fetch


class ContreeDockerBuilder:
    """Build a Dockerfile from `context`.

    Applies each directive against a content-addressed layer cache keyed by
    the build's session.
    """

    context_class: type[BuildContext] = BuildContext

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        store: SyncStore | None = None,
        cache: SyncCache | None = None,
        http_fetch: Callable[[str, str, Iterable[tuple[str, str]]], FetchResponse] | None = None,
        parser: DockerfileParser | None = None,
        session_factory: Callable[..., ContreeSession] | None = None,
    ) -> None:
        self.client = client
        self.store = store if store is not None else SyncMemoryStore()
        self.cache = cache if cache is not None else SyncMemoryCache()
        self.http_fetch = http_fetch or default_http_fetch
        self.parser = parser if parser is not None else DockerfileParser()
        self.session_factory = session_factory if session_factory is not None else ContreeSession
        self.ctx: BuildContext | None = None

    @property
    def session(self) -> ContreeSession | None:
        return self.ctx.session if self.ctx is not None else None

    def build(
        self,
        context: str | Path,
        *,
        dockerfile: str | Path | None = None,
        tag: str | None = None,
        build_args: dict[str, str] | None = None,
        no_cache: bool = False,
        timeout: int = BUILD_TIMEOUT_DEFAULT,
        session_id: str | None = None,
        on_event: Callable[[BuildEvent], None] | None = None,
        on_step: Callable[[BuildStepEvent], None] | None = None,
    ) -> str:
        context_dir, dockerfile_path = resolve_build_paths(context, dockerfile)

        try:
            directives = self.parse(dockerfile_path.read_text())
        except ValueError as exc:
            raise ValueError(f"Dockerfile parse error: {exc}") from exc

        if not validate_first_directive(directives):
            raise ValueError("Dockerfile must contain a FROM directive")

        ctx = self.create_context(
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
                self.run_step(directive, ctx, index=index)
            except BaseException as exc:
                with suppress(BaseException):
                    if on_step is not None:
                        on_step(
                            BuildStepEvent(
                                index, repr(directive), False, image_before, None, time.monotonic() - start, exc
                            )
                        )
                raise
            if on_step is not None:
                on_step(
                    BuildStepEvent(
                        index,
                        repr(directive),
                        ctx.last_cache_hit,
                        image_before,
                        ctx.last_image or None,
                        time.monotonic() - start,
                        None,
                    )
                )
        self.finalize(ctx)

        if not ctx.last_image:
            raise DockerBuildError("build produced no image")

        if tag:
            self.client.update_image_tag(ctx.last_image, tag)

        return ctx.last_image

    def parse(self, text: str) -> list[DockerKeyword]:
        """Return build directives through the configured parser.

        Returns:
            The parsed directives in source order.

        """
        return self.parser.parse(text)

    def create_context(self, request: BuildRequest) -> BuildContext:
        """Construct per-build state using the public context and session factories.

        Returns:
            A context owned by this build invocation.

        """
        return self.context_class(
            client=self.client,
            store=self.store,
            cache=self.cache,
            local=LocalContext.from_dir(request.context_dir),
            http_fetch=self.http_fetch,
            session_factory=self.session_factory,
            directive_executor=self.run_step,
            session_id=request.session_id,
            build_args=dict(request.build_args),
            no_cache=request.no_cache,
            timeout=request.timeout,
        )

    def run_step(self, directive: DockerKeyword, context: BuildContext, *, index: int | None = None) -> None:
        """Report one directive execution, including nested and synthetic steps."""
        parent = context.progress.current
        parent_cache_hit = context.last_cache_hit
        context.progress.start(repr(directive), index, context.last_image or None)
        context.last_cache_hit = False
        try:
            context.emit_event("step_started")
            self.execute_directive(directive, context)
            if context.last_cache_hit:
                context.emit_event("cache_hit")
            context.emit_event("step_completed")
        except BaseException as error:
            with suppress(BaseException):
                context.emit_event("step_failed", error=error)
            raise
        finally:
            context.progress.current = parent
            if parent is not None:
                context.last_cache_hit = parent_cache_hit

    def execute_directive(self, directive: DockerKeyword, context: BuildContext) -> None:  # noqa: PLR6301 - public extension contract
        """Execute one directive. Override for policy checks or instrumentation."""
        directive.execute(context)

    def finalize(self, context: BuildContext) -> None:
        """Commit pending file attachments through the same directive execution hook."""
        if context.pending:
            self.run_step(RunKeyword(parts=(":",), shell_form=True), context)
