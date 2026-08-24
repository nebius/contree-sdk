"""Mutable state shared across one build invocation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.cache import AsyncCache, SyncCache
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.sync import ContreeSession
from contree_sdk.store import AsyncStore, SyncStore
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec

from .keyword import substitute
from .local_context import LocalContext
from .url_fetch import AsyncFetchResponse, FetchResponse
from .url_fetch import http_fetch as default_http_fetch
from .url_fetch import http_fetch_async as default_http_fetch_async


BUILD_TIMEOUT_DEFAULT = 600


@dataclass(frozen=True)
class BuildStepEvent:
    """Reported to `on_step` around each directive's `execute()`/`execute_async()` call."""

    index: int
    keyword: str
    cache_hit: bool
    image_before: str | None
    image_after: str | None
    duration: float
    error: BaseException | None = None


@dataclass
class PendingFile:
    instance_path: str
    file_uuid: str
    sha256: str
    uid: int
    gid: int
    mode: str  # octal like "0644"


def upload_file_spec_for(pending: PendingFile) -> UploadFileSpec:
    # the file is already uploaded (file_uuid known) - UploadedFile makes session.run()'s
    # own upload_file() reuse it directly instead of re-hashing/re-uploading the content
    uploaded = UploadedFile(uuid=pending.file_uuid, sha256=pending.sha256)
    return UploadFileSpec(uid=pending.uid, gid=pending.gid, mode=int(pending.mode, 8), source=uploaded)


@dataclass
class BuildContext:
    client: ContreeSyncClient
    store: SyncStore
    cache: SyncCache
    local: LocalContext
    http_fetch: Callable[[str, str, Iterable[tuple[str, str]]], FetchResponse] = default_http_fetch
    session_id: str = ""
    session: ContreeSession | None = None
    build_args: dict[str, str] = field(default_factory=dict)
    declared_args: set[str] = field(default_factory=set)
    arg_defaults: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    workdir: str = "/"
    user: str = ""
    parent_hash: str = ""
    # Sealed build stages: every FROM past the first closes the stage
    # before it. `stages` maps `FROM ... AS name` aliases, `stage_images`
    # indexes the same images for numeric `COPY --from=N` references.
    stages: dict[str, str] = field(default_factory=dict)
    stage_images: list[str] = field(default_factory=list)
    current_stage_alias: str = ""
    pending: list[PendingFile] = field(default_factory=list)
    no_cache: bool = False
    timeout: int = BUILD_TIMEOUT_DEFAULT
    last_cache_hit: bool = False

    def arg_values(self) -> dict[str, str]:
        # effective value for every declared ARG (build-arg overrides default)
        return {name: self.build_args.get(name, self.arg_defaults.get(name, "")) for name in self.declared_args}

    def substitute(self, text: str) -> str:
        merged = {**self.arg_values(), **self.env}
        return substitute(text, merged)

    def state_repr(self) -> str:
        return json.dumps(
            {
                "workdir": self.workdir,
                "user": self.user,
                "env": sorted(self.env.items()),
                "args": sorted(self.arg_values().items()),
            },
            sort_keys=True,
        )

    def pending_repr(self) -> str:
        return json.dumps(
            [
                {"path": p.instance_path, "sha": p.sha256, "uid": p.uid, "gid": p.gid, "mode": p.mode}
                for p in self.pending
            ],
            sort_keys=True,
        )

    def chain(self, contribution: str) -> str:
        digest = hashlib.sha256()
        digest.update(self.parent_hash.encode())
        digest.update(b"\x00")
        digest.update(self.state_repr().encode())
        digest.update(b"\x00")
        digest.update(contribution.encode())
        digest.update(b"\x00")
        digest.update(self.pending_repr().encode())
        return digest.hexdigest()

    @staticmethod
    def short_hash(full: str) -> str:
        return full[:16]

    @property
    def last_image(self) -> str:
        return (self.session.image_uuid or "") if self.session is not None else ""

    def pending_files_payload(self) -> dict[str, str | Path | bytes | UploadFileSpec]:
        return {p.instance_path: upload_file_spec_for(p) for p in self.pending}

    def try_cache_hit(self, branch_name: str) -> str | None:
        # cached image_uuid if `branch_name` exists, succeeded, and caching is enabled, else None
        if self.no_cache:
            return None
        tip = self.store.tip(self.session_id, branch=branch_name)
        if tip is None or tip.exit_code not in {None, 0}:
            return None
        if self.session is None:
            self.session = ContreeSession(
                self.client, session_id=self.session_id, store=self.store, image=tip.image_uuid
            )
        else:
            self.session.switch_branch(branch_name)
        self.last_cache_hit = True
        return tip.image_uuid

    def commit_layer(
        self, branch_name: str, image_uuid: str, *, kind: str, title: str, operation_uuid: str = ""
    ) -> None:
        # materialize a layer branch pointing at `image_uuid` and make it active
        existing_tip = self.store.tip(self.session_id, branch=branch_name)
        parent_id = existing_tip.id if existing_tip is not None else None
        self.store.append(
            self.session_id,
            image_uuid=image_uuid,
            parent_id=parent_id,
            kind=kind,
            title=title,
            operation_uuid=operation_uuid or None,
            branch=branch_name,
        )
        if self.session is None:
            self.store.switch_branch(self.session_id, branch_name)
            self.session = ContreeSession(self.client, session_id=self.session_id, store=self.store, image=image_uuid)
        else:
            self.session.switch_branch(branch_name)


@dataclass
class AsyncBuildContext:
    client: ContreeAsyncClient
    store: AsyncStore
    cache: AsyncCache
    local: LocalContext
    http_fetch_async: Callable[[str, str, Iterable[tuple[str, str]]], Awaitable[AsyncFetchResponse]] = (
        default_http_fetch_async
    )
    session_id: str = ""
    session: ContreeAsyncSession | None = None
    build_args: dict[str, str] = field(default_factory=dict)
    declared_args: set[str] = field(default_factory=set)
    arg_defaults: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    workdir: str = "/"
    user: str = ""
    parent_hash: str = ""
    stages: dict[str, str] = field(default_factory=dict)
    stage_images: list[str] = field(default_factory=list)
    current_stage_alias: str = ""
    pending: list[PendingFile] = field(default_factory=list)
    no_cache: bool = False
    timeout: int = BUILD_TIMEOUT_DEFAULT
    last_cache_hit: bool = False

    def arg_values(self) -> dict[str, str]:
        return {name: self.build_args.get(name, self.arg_defaults.get(name, "")) for name in self.declared_args}

    def substitute(self, text: str) -> str:
        merged = {**self.arg_values(), **self.env}
        return substitute(text, merged)

    def state_repr(self) -> str:
        return json.dumps(
            {
                "workdir": self.workdir,
                "user": self.user,
                "env": sorted(self.env.items()),
                "args": sorted(self.arg_values().items()),
            },
            sort_keys=True,
        )

    def pending_repr(self) -> str:
        return json.dumps(
            [
                {"path": p.instance_path, "sha": p.sha256, "uid": p.uid, "gid": p.gid, "mode": p.mode}
                for p in self.pending
            ],
            sort_keys=True,
        )

    def chain(self, contribution: str) -> str:
        digest = hashlib.sha256()
        digest.update(self.parent_hash.encode())
        digest.update(b"\x00")
        digest.update(self.state_repr().encode())
        digest.update(b"\x00")
        digest.update(contribution.encode())
        digest.update(b"\x00")
        digest.update(self.pending_repr().encode())
        return digest.hexdigest()

    @staticmethod
    def short_hash(full: str) -> str:
        return full[:16]

    @property
    def last_image(self) -> str:
        return (self.session.image_uuid or "") if self.session is not None else ""

    def pending_files_payload(self) -> dict[str, str | Path | bytes | UploadFileSpec]:
        return {p.instance_path: upload_file_spec_for(p) for p in self.pending}

    async def try_cache_hit(self, branch_name: str) -> str | None:
        # cached image_uuid if `branch_name` exists, succeeded, and caching is enabled, else None
        if self.no_cache:
            return None
        tip = await self.store.tip(self.session_id, branch=branch_name)
        if tip is None or tip.exit_code not in {None, 0}:
            return None
        if self.session is None:
            self.session = ContreeAsyncSession(
                self.client, session_id=self.session_id, store=self.store, image=tip.image_uuid
            )
        else:
            await self.session.switch_branch(branch_name)
        self.last_cache_hit = True
        return tip.image_uuid

    async def commit_layer(
        self, branch_name: str, image_uuid: str, *, kind: str, title: str, operation_uuid: str = ""
    ) -> None:
        existing_tip = await self.store.tip(self.session_id, branch=branch_name)
        parent_id = existing_tip.id if existing_tip is not None else None
        await self.store.append(
            self.session_id,
            image_uuid=image_uuid,
            parent_id=parent_id,
            kind=kind,
            title=title,
            operation_uuid=operation_uuid or None,
            branch=branch_name,
        )
        if self.session is None:
            await self.store.switch_branch(self.session_id, branch_name)
            self.session = ContreeAsyncSession(
                self.client, session_id=self.session_id, store=self.store, image=image_uuid
            )
        else:
            await self.session.switch_branch(branch_name)


def resolve_stage_ref(ctx: BuildContext | AsyncBuildContext, ref: str) -> str | None:
    # a numeric ref addresses a sealed stage by position (must be in range); a name is
    # looked up in the alias registry; anything else falls through to external resolution
    if ref.isdigit():
        index = int(ref)
        if index >= len(ctx.stage_images):
            raise ValueError(f"stage index out of range ({len(ctx.stage_images)} stage(s) sealed so far): {ref}")
        return ctx.stage_images[index]
    return ctx.stages.get(ref)


def resolve_build_paths(context: str | Path, dockerfile: str | Path | None) -> tuple[Path, Path]:
    context_dir = Path(context).resolve()
    if not context_dir.is_dir():
        raise FileNotFoundError(f"build context not found: {context_dir}")
    dockerfile_path = Path(dockerfile).resolve() if dockerfile else context_dir / "Dockerfile"
    if not dockerfile_path.is_file():
        raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")
    return context_dir, dockerfile_path
