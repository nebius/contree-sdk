"""Cache immutable stage files and directory archives for COPY."""

from __future__ import annotations

import posixpath
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from typing import IO, cast

from contree_client.exceptions import NotFoundError
from contree_client.models import DirectoryList

from contree_sdk.exceptions import DockerBuildError
from contree_sdk.reuse import async_lookup_result, async_remember_result, lookup_result, remember_result
from contree_sdk.store import JSONValue

from .context import AsyncBuildContext, BuildContext


SOURCE_CACHE_NAMESPACE = "docker.copy-source"
SPOOL_MAX_MEMORY = 8 * 1024 * 1024
MAX_SOURCE_SYMLINKS = 40


@dataclass(frozen=True)
class CopySource:
    uuid: str = ""
    sha256: str = ""
    is_dir: bool = False
    uid: int = 0
    gid: int = 0
    mode: int = 0o644
    # Relative archive paths and symlink flags, used only for explicit overrides.
    entries: tuple[tuple[str, bool], ...] = ()

    def data(self) -> dict[str, JSONValue]:
        data = asdict(self)
        data["entries"] = [list(entry) for entry in self.entries]
        return cast("dict[str, JSONValue]", data)

    @classmethod
    def from_data(cls, data: dict[str, JSONValue]) -> CopySource:
        return cls(
            uuid=cast("str", data["uuid"]),
            sha256=cast("str", data["sha256"]),
            is_dir=cast("bool", data["is_dir"]),
            uid=cast("int", data["uid"]),
            gid=cast("int", data["gid"]),
            mode=cast("int", data["mode"]),
            entries=tuple(
                (cast("str", item[0]), cast("bool", item[1])) for item in cast("list[list[JSONValue]]", data["entries"])
            ),
        )


def source_info(listing: DirectoryList, path: str) -> CopySource | str:
    if path == "/":
        return CopySource(is_dir=True)
    for item in listing.files:
        if item.path == posixpath.basename(path):
            if item.is_symlink:
                return posixpath.normpath(posixpath.join(posixpath.dirname(path), item.symlink_to))
            if not (item.is_dir or item.is_regular):
                raise DockerBuildError(f"COPY --from: unsupported source type: {path}")
            return CopySource(is_dir=item.is_dir, uid=item.uid, gid=item.gid, mode=item.mode & 0o7777)
    raise DockerBuildError(f"COPY --from: source not found: {path}")


def inspect_source(ctx: BuildContext, image: str, path: str) -> tuple[CopySource, str]:
    for _ in range(MAX_SOURCE_SYMLINKS):
        info = source_info(ctx.client.inspect_image_list(image, posixpath.dirname(path)), path)
        if isinstance(info, CopySource):
            return info, path
        path = info
    raise DockerBuildError(f"COPY --from: too many symlinks resolving {path}")


async def inspect_source_async(ctx: AsyncBuildContext, image: str, path: str) -> tuple[CopySource, str]:
    for _ in range(MAX_SOURCE_SYMLINKS):
        info = source_info(await ctx.client.inspect_image_list(image, posixpath.dirname(path)), path)
        if isinstance(info, CopySource):
            return info, path
        path = info
    raise DockerBuildError(f"COPY --from: too many symlinks resolving {path}")


def archive_entries(buffer: IO[bytes]) -> tuple[tuple[str, bool], ...]:
    with tarfile.open(fileobj=buffer, mode="r:") as archive:
        entries = []
        for member in archive:
            if posixpath.isabs(member.name) or ".." in member.name.split("/"):
                raise DockerBuildError(f"COPY --from: unsafe archive path: {member.name}")
            entries.append((posixpath.normpath(member.name), member.issym()))
    buffer.seek(0)
    return tuple(entries)


def export_source(ctx: BuildContext, image: str, path: str) -> CopySource:
    namespace = ctx.cache_namespace(SOURCE_CACHE_NAMESPACE)
    fingerprint = f"{image}:{path}"
    cached = lookup_result(ctx.store, namespace, fingerprint)
    if cached is not None and ctx.client.check_file_exists(cast("str", cached["sha256"])):
        return CopySource.from_data(cached)
    try:  # noqa: PLW0717 - translate missing source errors from metadata and streaming
        info, source_path = inspect_source(ctx, image, path)
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY) as buffer:
            chunks = (
                ctx.client.inspect_image_archive(image, source_path, compressed=False)
                if info.is_dir
                else ctx.client.inspect_image_download_stream(image, source_path)
            )
            for chunk in chunks:
                buffer.write(chunk)
            buffer.seek(0)
            entries = archive_entries(buffer) if info.is_dir else ()
            uploaded = ctx.client.ensure_file(buffer)
    except NotFoundError:
        raise DockerBuildError(f"COPY --from: {path} not found in {image}") from None
    result = CopySource(str(uploaded.uuid), str(uploaded.sha256), info.is_dir, info.uid, info.gid, info.mode, entries)
    remember_result(ctx.store, namespace, fingerprint, result.data())
    return result


async def export_source_async(ctx: AsyncBuildContext, image: str, path: str) -> CopySource:
    namespace = ctx.cache_namespace(SOURCE_CACHE_NAMESPACE)
    fingerprint = f"{image}:{path}"
    cached = await async_lookup_result(ctx.store, namespace, fingerprint)
    if cached is not None and await ctx.client.check_file_exists(cast("str", cached["sha256"])):
        return CopySource.from_data(cached)
    try:  # noqa: PLW0717 - translate missing source errors from metadata and streaming
        info, source_path = await inspect_source_async(ctx, image, path)
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY) as buffer:
            chunks = (
                ctx.client.inspect_image_archive(image, source_path, compressed=False)
                if info.is_dir
                else ctx.client.inspect_image_download_stream(image, source_path)
            )
            async for chunk in chunks:
                buffer.write(chunk)
            buffer.seek(0)
            entries = archive_entries(buffer) if info.is_dir else ()
            uploaded = await ctx.client.ensure_file(buffer)
    except NotFoundError:
        raise DockerBuildError(f"COPY --from: {path} not found in {image}") from None
    result = CopySource(str(uploaded.uuid), str(uploaded.sha256), info.is_dir, info.uid, info.gid, info.mode, entries)
    await async_remember_result(ctx.store, namespace, fingerprint, result.data())
    return result
