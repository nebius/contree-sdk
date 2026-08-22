"""`FROM image[:tag] [AS name]` - set the base image for the build."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import ClassVar

from contree_client.exceptions import NotFoundError
from contree_client.models import ImageImportRegistry

from contree_sdk.session.base import require_str

from .context import AsyncBuildContext, BuildContext, resolve_stage_ref
from .keyword import DockerKeyword
from .kw_run import RunKeyword


DOCKER_HUB = "docker.io"
FROM_WITH_ALIAS_PARTS = 3


@dataclass(frozen=True, repr=False)
class FromKeyword(DockerKeyword):
    NAME: ClassVar[str] = "FROM"
    image_ref: str = ""
    alias: str = ""

    def __repr__(self) -> str:
        if self.alias:
            return f"FROM {self.image_ref} AS {self.alias}"
        return f"FROM {self.image_ref}"

    @classmethod
    def parse(cls, args_text: str) -> FromKeyword:
        raw = args_text.strip()
        if not raw:
            raise ValueError("FROM requires an image reference")
        parts = raw.split()
        if len(parts) == 1:
            return cls(image_ref=parts[0], alias="")
        if len(parts) == FROM_WITH_ALIAS_PARTS and parts[1].upper() == "AS":
            return cls(image_ref=parts[0], alias=parts[2])
        raise ValueError(f"invalid FROM syntax: {raw!r}")

    def serialize(self) -> str:
        return f"FROM {self.image_ref}" + (f" AS {self.alias}" if self.alias else "")

    def execute(self, ctx: BuildContext) -> None:
        if ctx.last_image:
            seal_stage(ctx)
        ctx.current_stage_alias = self.alias
        ctx.env.clear()
        ctx.workdir = "/"
        ctx.user = ""

        ref = ctx.substitute(self.image_ref)
        image_uuid = resolve_stage_ref(ctx, ref)
        if image_uuid is None:
            image_uuid = resolve_or_import(ctx, ref)

        from_hash = hashlib.sha256(f"FROM:{image_uuid}".encode()).hexdigest()
        branch_name = f"layer:{ctx.short_hash(from_hash)}"

        ctx.pending.clear()
        if ctx.try_cache_hit(branch_name) is not None:
            ctx.parent_hash = from_hash
            return

        ctx.commit_layer(branch_name, image_uuid, kind="use", title=f"FROM {ref}")
        ctx.parent_hash = from_hash

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        if ctx.last_image:
            await seal_stage_async(ctx)
        ctx.current_stage_alias = self.alias
        ctx.env.clear()
        ctx.workdir = "/"
        ctx.user = ""

        ref = ctx.substitute(self.image_ref)
        image_uuid = resolve_stage_ref(ctx, ref)
        if image_uuid is None:
            image_uuid = await resolve_or_import_async(ctx, ref)

        from_hash = hashlib.sha256(f"FROM:{image_uuid}".encode()).hexdigest()
        branch_name = f"layer:{ctx.short_hash(from_hash)}"

        ctx.pending.clear()
        if await ctx.try_cache_hit(branch_name) is not None:
            ctx.parent_hash = from_hash
            return

        await ctx.commit_layer(branch_name, image_uuid, kind="use", title=f"FROM {ref}")
        ctx.parent_hash = from_hash


def seal_stage(ctx: BuildContext) -> None:
    """Close the stage in progress before the next FROM starts.

    Pending files exist only as attachments for a future RUN, so a stage
    that ends with COPY/ADD is committed through the same trivial closer
    that `finalize_pending` uses; the sealed image then becomes addressable
    via `COPY --from=<alias|index>`.
    """
    if ctx.pending:
        # Sealing just commits already-uploaded files; it must run as root
        # regardless of the stage's active USER.
        saved_user = ctx.user
        ctx.user = ""
        try:
            RunKeyword(parts=(":",), shell_form=True).execute(ctx)
        finally:
            ctx.user = saved_user
    ctx.stage_images.append(ctx.last_image)
    if ctx.current_stage_alias:
        ctx.stages[ctx.current_stage_alias] = ctx.last_image


async def seal_stage_async(ctx: AsyncBuildContext) -> None:
    if ctx.pending:
        saved_user = ctx.user
        ctx.user = ""
        try:
            await RunKeyword(parts=(":",), shell_form=True).execute_async(ctx)
        finally:
            ctx.user = saved_user
    ctx.stage_images.append(ctx.last_image)
    if ctx.current_stage_alias:
        ctx.stages[ctx.current_stage_alias] = ctx.last_image


def normalize_registry_url(ref: str) -> str:
    # normalise an image reference to docker://registry/path:tag
    if ref.startswith("docker://"):
        return ref

    parts = ref.split("/")
    if len(parts) == 1:
        registry = DOCKER_HUB
        image_path = f"library/{parts[0]}"
    elif "." in parts[0] or ":" in parts[0]:
        registry = parts[0]
        remaining = "/".join(parts[1:])
        image_path = f"library/{remaining}" if registry == DOCKER_HUB and "/" not in remaining else remaining
    else:
        registry = DOCKER_HUB
        image_path = "/".join(parts)

    last_segment = image_path.rsplit("/", 1)[-1]
    if ":" not in last_segment:
        image_path += ":latest"

    return f"docker://{registry}/{image_path}"


def resolve_or_import(ctx: BuildContext, ref: str) -> str:
    # resolve ref to a UUID, importing from a registry on a miss
    try:
        return ctx.client.resolve_image(ref)
    except NotFoundError:
        pass

    url = normalize_registry_url(ref)
    tag = ref if not ref.startswith("docker://") else url.removeprefix("docker://")
    op_uuid = ctx.client.import_image(
        ImageImportRegistry(url=url), tag=tag, timeout=ctx.timeout if ctx.timeout else ...
    )
    operation = ctx.client.wait_operation(op_uuid, timeout=ctx.timeout if ctx.timeout else None)
    return require_str(operation.result_image_uuid, f"image import {tag!r} produced no image")


async def resolve_or_import_async(ctx: AsyncBuildContext, ref: str) -> str:
    try:
        return await ctx.client.resolve_image(ref)
    except NotFoundError:
        pass

    url = normalize_registry_url(ref)
    tag = ref if not ref.startswith("docker://") else url.removeprefix("docker://")
    op_uuid = await ctx.client.import_image(
        ImageImportRegistry(url=url), tag=tag, timeout=ctx.timeout if ctx.timeout else ...
    )
    operation = await ctx.client.wait_operation(op_uuid, timeout=ctx.timeout if ctx.timeout else None)
    return require_str(operation.result_image_uuid, f"image import {tag!r} produced no image")
