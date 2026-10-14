"""`ADD [--chown=...] [--chmod=...] SRC... DEST` - file/dir/URL variant of COPY.

URL sources are fetched via the injectable `ctx.http_fetch`/`ctx.http_fetch_async`
callable and cached by URL (see `contree_sdk.cache.SyncCache`/`AsyncCache`):
a rebuild sends the previous response's `ETag`/`Last-Modified` back as
`If-None-Match`/`If-Modified-Since`, so an upstream that hasn't changed
answers `304 Not Modified` and the previously-uploaded file uuid is reused
without re-uploading (`http_fetch`/`http_fetch_async`'s default
implementations return an empty body for a 304, so no bytes are wasted
either). Local sources fall through to the same walker COPY uses.
"""

from __future__ import annotations

import hashlib
import posixpath
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import IO, Any, ClassVar

from contree_sdk.exceptions import DockerBuildError
from contree_sdk.file_io import run_file_io

from .context import AsyncBuildContext, BuildContext, PendingFile
from .keyword import DockerKeyword
from .kw_copy import format_copy_like, parse_chmod, parse_chown, parse_copy_like, stage_copy, stage_copy_async
from .url_fetch import HTTP_NOT_MODIFIED, is_url, url_basename


@dataclass(frozen=True, repr=False)
class AddKeyword(DockerKeyword):
    NAME: ClassVar[str] = "ADD"
    sources: tuple[str, ...] = field(default_factory=tuple)
    dest: str = ""
    chown: str = ""
    chmod: str = ""
    from_stage: str = ""

    def __repr__(self) -> str:
        return format_copy_like("ADD", self)

    @classmethod
    def parse(cls, args_text: str) -> AddKeyword:
        return cls(**parse_copy_like(args_text, "ADD"))

    def serialize(self) -> str:
        return f"ADD chown={self.chown} chmod={self.chmod} sources={self.sources!r} dest={self.dest}"

    def execute(self, ctx: BuildContext) -> None:
        if self.from_stage:
            raise DockerBuildError("ADD does not support --from; use COPY --from for stage copies")

        local_sources, url_sources = split_sources(ctx, self.sources)

        if url_sources:
            sub_dest = ctx.substitute(self.dest)
            if not posixpath.isabs(sub_dest):
                sub_dest = posixpath.normpath(posixpath.join(ctx.workdir or "/", sub_dest))
            stage_urls(
                ctx,
                tuple(url_sources),
                sub_dest,
                chown=ctx.substitute(self.chown),
                chmod=ctx.substitute(self.chmod),
                multi_source=len(self.sources) > 1,
            )

        if local_sources:
            stage_copy(ctx, tuple(local_sources), self.dest, self.chown, self.chmod)

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        if self.from_stage:
            raise DockerBuildError("ADD does not support --from; use COPY --from for stage copies")

        local_sources, url_sources = split_sources(ctx, self.sources)

        if url_sources:
            sub_dest = ctx.substitute(self.dest)
            if not posixpath.isabs(sub_dest):
                sub_dest = posixpath.normpath(posixpath.join(ctx.workdir or "/", sub_dest))
            await stage_urls_async(
                ctx,
                tuple(url_sources),
                sub_dest,
                chown=ctx.substitute(self.chown),
                chmod=ctx.substitute(self.chmod),
                multi_source=len(self.sources) > 1,
            )

        if local_sources:
            await stage_copy_async(ctx, tuple(local_sources), self.dest, self.chown, self.chmod)


def split_sources(ctx: BuildContext | AsyncBuildContext, sources: tuple[str, ...]) -> tuple[list[str], list[str]]:
    local_sources: list[str] = []
    url_sources: list[str] = []
    for raw in sources:
        value = ctx.substitute(raw)
        (url_sources if is_url(value) else local_sources).append(value)
    return local_sources, url_sources


URL_CACHE_NAMESPACE = "docker.fetch"


def conditional_headers_for(cached: Any) -> list[tuple[str, str]]:
    if not isinstance(cached, dict):
        return []
    headers: list[tuple[str, str]] = []
    if cached.get("etag"):
        headers.append(("If-None-Match", str(cached["etag"])))
    if cached.get("last_modified"):
        headers.append(("If-Modified-Since", str(cached["last_modified"])))
    return headers


def cached_uuid_sha256(cached: Any) -> tuple[str, str] | None:
    if isinstance(cached, dict) and "uuid" in cached and "sha256" in cached:
        return str(cached["uuid"]), str(cached["sha256"])
    return None


def unchanged_by_etag(cached: Any, etag: str | None) -> bool:
    # a fallback for servers that don't honor If-None-Match and always answer 200:
    # if the freshly-fetched ETag still matches the cached one, the content is unchanged
    return bool(etag) and isinstance(cached, dict) and cached.get("etag") == etag


def iter_url_body(body: Iterable[bytes]) -> Iterator[bytes]:
    read = getattr(body, "read", None)
    if read is None:
        yield from body
    else:
        while chunk := read(64 * 1024):
            yield chunk


def write_url_chunk(handle: IO[bytes], chunk: bytes, digest: Any) -> None:
    handle.write(chunk)
    digest.update(chunk)


def fetch_url(ctx: BuildContext, url: str) -> tuple[str, str]:
    cached = ctx.cache.get(url, namespace=ctx.cache_namespace(URL_CACHE_NAMESPACE))
    status, headers, body = ctx.http_fetch(url, "GET", conditional_headers_for(cached))
    with tempfile.TemporaryFile() as content:
        digest = hashlib.sha256()
        try:
            for chunk in iter_url_body(body):
                write_url_chunk(content, chunk, digest)
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()
        if status == HTTP_NOT_MODIFIED:
            hit = cached_uuid_sha256(cached)
            if hit is None:
                raise DockerBuildError("URL returned 304 without a valid cached upload")
            ctx.file_sources.record(hit[0], hit[1], url, kind="url")
            return hit
        if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            raise DockerBuildError(f"URL download failed with HTTP {status}")

        header_map = {key.lower(): value for key, value in headers}
        etag = header_map.get("etag")
        last_modified = header_map.get("last-modified")
        if unchanged_by_etag(cached, etag):
            hit = cached_uuid_sha256(cached)
            if hit is not None:
                ctx.file_sources.record(hit[0], hit[1], url, kind="url")
                return hit

        sha256 = digest.hexdigest()
        content.seek(0)
        stored = ctx.client.ensure_file(content, sha256=sha256)
    file_uuid = str(stored.uuid)
    ctx.cache.set(
        url,
        {"uuid": file_uuid, "sha256": sha256, "etag": etag, "last_modified": last_modified},
        namespace=ctx.cache_namespace(URL_CACHE_NAMESPACE),
        ttl=ctx.upload_cache_ttl,
    )
    ctx.file_sources.record(file_uuid, sha256, url, kind="url")
    return file_uuid, sha256


def stage_urls(
    ctx: BuildContext, urls: tuple[str, ...], dest: str, *, chown: str, chmod: str, multi_source: bool
) -> None:
    uid, gid = parse_chown(chown)
    mode_override = parse_chmod(chmod)
    dest_is_dir = dest.endswith("/") or multi_source

    for url in urls:
        file_uuid, sha256 = fetch_url(ctx, url)
        instance_path = posixpath.join(dest.rstrip("/"), url_basename(url)) if dest_is_dir else dest
        mode = mode_override if mode_override is not None else 0o644
        ctx.pending.append(
            PendingFile(
                instance_path=instance_path, file_uuid=file_uuid, sha256=sha256, uid=uid, gid=gid, mode=f"{mode:04o}"
            )
        )


async def fetch_url_async(ctx: AsyncBuildContext, url: str) -> tuple[str, str]:
    cached = await ctx.cache.get(url, namespace=ctx.cache_namespace(URL_CACHE_NAMESPACE))
    status, headers, body = await ctx.http_fetch_async(url, "GET", conditional_headers_for(cached))
    with tempfile.TemporaryFile() as content:
        digest = hashlib.sha256()
        try:
            async for chunk in body:
                await run_file_io(write_url_chunk, content, chunk, digest)
        finally:
            close = getattr(body, "aclose", None)
            if close is not None:
                await close()
        if status == HTTP_NOT_MODIFIED:
            hit = cached_uuid_sha256(cached)
            if hit is None:
                raise DockerBuildError("URL returned 304 without a valid cached upload")
            await ctx.file_sources.record(hit[0], hit[1], url, kind="url")
            return hit
        if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            raise DockerBuildError(f"URL download failed with HTTP {status}")

        header_map = {key.lower(): value for key, value in headers}
        etag = header_map.get("etag")
        last_modified = header_map.get("last-modified")
        if unchanged_by_etag(cached, etag):
            hit = cached_uuid_sha256(cached)
            if hit is not None:
                await ctx.file_sources.record(hit[0], hit[1], url, kind="url")
                return hit

        sha256 = digest.hexdigest()
        await run_file_io(content.seek, 0)
        stored = await ctx.client.ensure_file(content, sha256=sha256)
    file_uuid = str(stored.uuid)
    await ctx.cache.set(
        url,
        {"uuid": file_uuid, "sha256": sha256, "etag": etag, "last_modified": last_modified},
        namespace=ctx.cache_namespace(URL_CACHE_NAMESPACE),
        ttl=ctx.upload_cache_ttl,
    )
    await ctx.file_sources.record(file_uuid, sha256, url, kind="url")
    return file_uuid, sha256


async def stage_urls_async(
    ctx: AsyncBuildContext, urls: tuple[str, ...], dest: str, *, chown: str, chmod: str, multi_source: bool
) -> None:
    uid, gid = parse_chown(chown)
    mode_override = parse_chmod(chmod)
    dest_is_dir = dest.endswith("/") or multi_source

    for url in urls:
        file_uuid, sha256 = await fetch_url_async(ctx, url)
        instance_path = posixpath.join(dest.rstrip("/"), url_basename(url)) if dest_is_dir else dest
        mode = mode_override if mode_override is not None else 0o644
        ctx.pending.append(
            PendingFile(
                instance_path=instance_path, file_uuid=file_uuid, sha256=sha256, uid=uid, gid=gid, mode=f"{mode:04o}"
            )
        )
