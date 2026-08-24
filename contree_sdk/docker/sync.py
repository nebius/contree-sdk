"""Build a Dockerfile against a ConTree client (sync)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

from contree_client.types import ContreeSyncClient

from contree_sdk.cache import SyncCache, SyncMemoryCache
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.session.sync import ContreeSession
from contree_sdk.store import SyncMemoryStore, SyncStore

from .context import BUILD_TIMEOUT_DEFAULT, BuildContext, BuildStepEvent, resolve_build_paths
from .kw_run import RunKeyword
from .local_context import LocalContext
from .parser import make_session_key, parse_dockerfile, validate_first_directive
from .url_fetch import FetchResponse
from .url_fetch import http_fetch as default_http_fetch


class ContreeDockerBuilder:
    """Build a Dockerfile from `context`.

    Applies each directive against a content-addressed layer cache keyed by
    the build's session.
    """

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        store: SyncStore | None = None,
        cache: SyncCache | None = None,
        http_fetch: Callable[[str, str, Iterable[tuple[str, str]]], FetchResponse] | None = None,
    ) -> None:
        self.client = client
        self.store = store or SyncMemoryStore()
        self.cache = cache or SyncMemoryCache()
        self.http_fetch = http_fetch or default_http_fetch
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
        on_step: Callable[[BuildStepEvent], None] | None = None,
    ) -> str:
        context_dir, dockerfile_path = resolve_build_paths(context, dockerfile)

        try:
            directives = parse_dockerfile(dockerfile_path.read_text())
        except ValueError as exc:
            raise ValueError(f"Dockerfile parse error: {exc}") from exc

        if not validate_first_directive(directives):
            raise ValueError("Dockerfile must contain a FROM directive")

        ctx = BuildContext(
            client=self.client,
            store=self.store,
            cache=self.cache,
            local=LocalContext.from_dir(context_dir),
            http_fetch=self.http_fetch,
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
                directive.execute(ctx)
            except BaseException as exc:
                if on_step is not None:
                    on_step(
                        BuildStepEvent(index, repr(directive), False, image_before, None, time.monotonic() - start, exc)
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
        finalize_pending(ctx)

        if not ctx.last_image:
            raise DockerBuildError("build produced no image")

        if tag:
            self.client.update_image_tag(ctx.last_image, tag)

        return ctx.last_image


def finalize_pending(ctx: BuildContext) -> None:
    """If COPY/ADD left files pending, commit them via a trivial RUN."""
    if not ctx.pending:
        return
    RunKeyword(parts=(":",), shell_form=True).execute(ctx)
