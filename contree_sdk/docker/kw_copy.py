"""`COPY [--from=...] [--chown=...] [--chmod=...] SRC... DEST`.

Local sources are uploaded from the build context and attached to the next
RUN. `--from=<stage|index|image>` sources are exported from the referenced
image as ordinary file attachments or directory archives. The live API
unpacks directories directly at their destination. Explicit directory
attribute overrides run before the VM is saved.
"""

from __future__ import annotations

import asyncio
import json
import posixpath
import shlex
from dataclasses import dataclass, field
from typing import ClassVar, TypedDict

from contree_sdk.files import UploadFileSpec
from contree_sdk.reuse import async_lookup_result, async_remember_result, lookup_result, remember_result
from contree_sdk.upload_cache import async_upload_snapshot, upload_snapshot

from .context import AsyncBuildContext, BuildContext, PendingFile, resolve_stage_ref
from .copy_layer import UploadedArchive, apply_copy_layer, apply_copy_layer_async
from .copy_source import CopySource, export_source, export_source_async
from .keyword import DockerKeyword
from .kw_from import resolve_or_import, resolve_or_import_async
from .local_context import MappedFile


MIN_COPY_LIKE_ARGS = 2
OVERRIDE_COMMAND_MAX_LENGTH = 16 * 1024


class CopyLikeArgs(TypedDict, total=False):
    sources: tuple[str, ...]
    dest: str
    chown: str
    chmod: str
    from_stage: str


@dataclass(frozen=True, repr=False)
class CopyKeyword(DockerKeyword):
    NAME: ClassVar[str] = "COPY"
    sources: tuple[str, ...] = field(default_factory=tuple)
    dest: str = ""
    chown: str = ""
    chmod: str = ""
    from_stage: str = ""

    def __repr__(self) -> str:
        return format_copy_like("COPY", self)

    @classmethod
    def parse(cls, args_text: str) -> CopyKeyword:
        return cls(**parse_copy_like(args_text, "COPY"))

    def serialize(self) -> str:
        return (
            f"COPY from={self.from_stage} chown={self.chown} chmod={self.chmod} "
            f"sources={json.dumps(list(self.sources))} dest={self.dest}"
        )

    def execute(self, ctx: BuildContext) -> None:
        if self.from_stage:
            copy_from_image(ctx, self.from_stage, self.sources, self.dest, self.chown, self.chmod)
            return
        stage_copy(ctx, self.sources, self.dest, self.chown, self.chmod)

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        if self.from_stage:
            await copy_from_image_async(ctx, self.from_stage, self.sources, self.dest, self.chown, self.chmod)
            return
        await stage_copy_async(ctx, self.sources, self.dest, self.chown, self.chmod)


def parse_copy_like(args_text: str, label: str) -> CopyLikeArgs:
    # shared shell-style parser for COPY and ADD; each class's own .parse() builds itself from the result
    raw = args_text.strip()
    if not raw:
        raise ValueError(f"{label} requires SRC and DEST")
    stripped = raw.lstrip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except ValueError as exc:
            raise ValueError(f"invalid JSON exec-form: {raw!r}") from exc
        valid = (
            isinstance(parsed, list) and len(parsed) >= MIN_COPY_LIKE_ARGS and all(isinstance(p, str) for p in parsed)
        )
        if not valid:
            raise ValueError(f"{label} exec-form must be a list of >=2 strings")
        return {"sources": tuple(parsed[:-1]), "dest": parsed[-1]}

    tokens = shlex.split(raw)
    chown = ""
    chmod = ""
    from_stage = ""
    positional: list[str] = []
    for token in tokens:
        if token.startswith("--chown="):
            chown = token.partition("=")[2]
        elif token.startswith("--chmod="):
            chmod = token.partition("=")[2]
        elif token.startswith("--from="):
            from_stage = token.partition("=")[2]
        elif token.startswith("--"):
            raise ValueError(f"unknown {label} option: {token!r}")
        else:
            positional.append(token)
    if len(positional) < MIN_COPY_LIKE_ARGS:
        raise ValueError(f"{label} requires at least one source and a destination")
    return {
        "sources": tuple(positional[:-1]),
        "dest": positional[-1],
        "chown": chown,
        "chmod": chmod,
        "from_stage": from_stage,
    }


def format_copy_like(name: str, kw: object) -> str:
    flags: list[str] = []
    chown = getattr(kw, "chown", "")
    chmod = getattr(kw, "chmod", "")
    from_stage = getattr(kw, "from_stage", "")
    if from_stage:
        flags.append(f"--from={from_stage}")
    if chown:
        flags.append(f"--chown={chown}")
    if chmod:
        flags.append(f"--chmod={chmod}")
    sources = list(getattr(kw, "sources", ()))
    dest = getattr(kw, "dest", "")
    return " ".join([name, *flags, *sources, dest])


def parse_chown(spec: str) -> tuple[int, int]:
    if not spec:
        return 0, 0
    user, _, group = spec.partition(":")
    uid = resolve_id(user) if user else 0
    gid = resolve_id(group) if group else uid
    return uid, gid


def parse_chmod(spec: str) -> int | None:
    if not spec:
        return None
    try:
        return int(spec, 8)
    except ValueError:
        raise ValueError(f"invalid chmod value: {spec!r}") from None


def resolve_id(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


# -- local file cache (content sha256 -> uploaded uuid) --

LOCAL_FILE_CACHE_NAMESPACE = "docker.copy"


def cached_local_uuid(ctx: BuildContext, sha256: str) -> str | None:
    cached = lookup_result(ctx.store, ctx.cache_namespace(LOCAL_FILE_CACHE_NAMESPACE), sha256)
    if isinstance(cached, dict) and cached.get("uuid"):
        return str(cached["uuid"])
    return None


def record_local_uuid(ctx: BuildContext, sha256: str, file_uuid: str) -> None:
    remember_result(
        ctx.store,
        ctx.cache_namespace(LOCAL_FILE_CACHE_NAMESPACE),
        sha256,
        {"uuid": file_uuid},
        ttl=ctx.upload_cache_ttl,
    )


def upload_files(ctx: BuildContext, files: list[MappedFile]) -> dict[str, tuple[str, str]]:
    uploaded: dict[str, tuple[str, str]] = {}
    for mf in files:
        with upload_snapshot(UploadFileSpec(source=mf.host_path)) as snapshot:
            sha256 = snapshot.sha256
            file_uuid = cached_local_uuid(ctx, sha256)
            if file_uuid is None:
                with snapshot.open() as handle:
                    stored = ctx.client.ensure_file(handle, sha256=sha256)
                file_uuid = str(stored.uuid)
                record_local_uuid(ctx, sha256, file_uuid)
            uploaded[mf.host_path] = (file_uuid, sha256)
            ctx.file_sources.record(file_uuid, sha256, mf.host_path)
    return uploaded


def stage_copy(ctx: BuildContext, sources: tuple[str, ...], dest: str, chown: str, chmod: str) -> None:
    """Resolve sources via `LocalContext`, upload, append to `ctx.pending`."""
    sub_sources = tuple(ctx.substitute(s) for s in sources)
    sub_dest = ctx.substitute(dest)
    sub_chown = ctx.substitute(chown)
    sub_chmod = ctx.substitute(chmod)

    if not posixpath.isabs(sub_dest):
        sub_dest = posixpath.normpath(posixpath.join(ctx.workdir or "/", sub_dest))

    uid, gid = parse_chown(sub_chown)
    mode_override = parse_chmod(sub_chmod)

    mapped = ctx.local.collect(sub_sources, sub_dest, uid=uid, gid=gid, mode_override=mode_override)
    if not mapped:
        return

    uploaded = upload_files(ctx, mapped)
    for mf in mapped:
        file_uuid, sha256 = uploaded[mf.host_path]
        ctx.pending.append(pending_file_for(mf, file_uuid=file_uuid, sha256=sha256))


def resolve_stage_image(ctx: BuildContext, ref: str) -> str:
    # map a `--from` reference (stage alias/index, or external image) to an image UUID
    local = resolve_stage_ref(ctx, ref)
    if local is not None:
        return local
    return resolve_or_import(ctx, ref)


def resolve_image_copy(
    ctx: BuildContext | AsyncBuildContext, image_uuid: str, sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> CopyKeyword:
    target = ctx.substitute(dest)
    is_directory = target.endswith("/") or len(sources) > 1
    target = posixpath.normpath(posixpath.join(ctx.workdir or "/", target))
    return CopyKeyword(
        from_stage=image_uuid,
        sources=tuple(posixpath.normpath(posixpath.join("/", ctx.substitute(src))) for src in sources),
        dest=target.rstrip("/") + "/" if is_directory else target,
        chown=ctx.substitute(chown),
        chmod=ctx.substitute(chmod),
    )


def stage_image_file(ctx: BuildContext | AsyncBuildContext, source: CopySource, path: str, copy: CopyKeyword) -> None:
    destination = posixpath.join(copy.dest, posixpath.basename(path)) if copy.dest.endswith("/") else copy.dest
    uid, gid = parse_chown(copy.chown) if copy.chown else (source.uid, source.gid)
    mode = parse_chmod(copy.chmod)
    ctx.pending.append(
        PendingFile(destination, source.uuid, source.sha256, uid, gid, f"{source.mode if mode is None else mode:04o}")
    )


def directory_overrides(source: CopySource, copy: CopyKeyword) -> list[str]:
    # Apply explicit attributes only to archive entries, in bounded subprocess batches.
    commands = []
    destination = posixpath.normpath(copy.dest)
    uid, gid = parse_chown(copy.chown)
    mode = parse_chmod(copy.chmod)
    for name, symlink in source.entries:
        path = shlex.quote(posixpath.normpath(posixpath.join(destination, name)))
        if copy.chown:
            commands.append(f"chown -h {uid}:{gid} {path}")
        if mode is not None and not symlink:
            commands.append(f"chmod {mode:o} {path}")
    batches: list[str] = []
    for command in commands:
        if not batches or len(batches[-1]) + len(command) > OVERRIDE_COMMAND_MAX_LENGTH:
            batches.append(command)
        else:
            batches[-1] += " && " + command
    return batches


def copy_from_image(
    ctx: BuildContext, from_stage: str, sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> None:
    image = resolve_stage_image(ctx, ctx.substitute(from_stage))
    copy = resolve_image_copy(ctx, image, sources, dest, chown, chmod)
    for path in copy.sources:
        directive = CopyKeyword(from_stage=image, sources=(path,), dest=copy.dest, chown=copy.chown, chmod=copy.chmod)
        chain = ctx.chain(directive.serialize())
        branch = f"layer:{chain}"
        if ctx.try_cache_hit(branch) is not None:
            ctx.parent_hash = chain
            ctx.pending.clear()
            continue
        source = export_source(ctx, image, path)
        if not source.is_dir:
            stage_image_file(ctx, source, path, copy)
            continue
        archive = UploadedArchive(source.uuid, posixpath.normpath(copy.dest))
        apply_copy_layer(ctx, archive, directory_overrides(source, copy), branch=branch)
        ctx.parent_hash = chain
        ctx.pending.clear()


def pending_file_for(mf: MappedFile, *, file_uuid: str, sha256: str) -> PendingFile:
    return PendingFile(
        instance_path=mf.instance_path,
        file_uuid=file_uuid,
        sha256=sha256,
        uid=mf.uid,
        gid=mf.gid,
        mode=f"{mf.mode:04o}",
    )


# -- async mirrors ---------------------------------------------------------


async def resolve_stage_image_async(ctx: AsyncBuildContext, ref: str) -> str:
    local = resolve_stage_ref(ctx, ref)
    if local is not None:
        return local
    return await resolve_or_import_async(ctx, ref)


async def cached_local_uuid_async(ctx: AsyncBuildContext, sha256: str) -> str | None:
    cached = await async_lookup_result(ctx.store, ctx.cache_namespace(LOCAL_FILE_CACHE_NAMESPACE), sha256)
    if isinstance(cached, dict) and cached.get("uuid"):
        return str(cached["uuid"])
    return None


async def record_local_uuid_async(ctx: AsyncBuildContext, sha256: str, file_uuid: str) -> None:
    await async_remember_result(
        ctx.store,
        ctx.cache_namespace(LOCAL_FILE_CACHE_NAMESPACE),
        sha256,
        {"uuid": file_uuid},
        ttl=ctx.upload_cache_ttl,
    )


async def upload_one_file_async(ctx: AsyncBuildContext, mf: MappedFile) -> tuple[str, str]:
    async with async_upload_snapshot(UploadFileSpec(source=mf.host_path)) as snapshot:
        sha256 = snapshot.sha256
        file_uuid = await cached_local_uuid_async(ctx, sha256)
        if file_uuid is None:
            with snapshot.open() as handle:
                stored = await ctx.client.ensure_file(handle, sha256=sha256)
            file_uuid = str(stored.uuid)
            await record_local_uuid_async(ctx, sha256, file_uuid)
        await ctx.file_sources.record(file_uuid, sha256, mf.host_path)
        return file_uuid, sha256


async def upload_files_async(ctx: AsyncBuildContext, files: list[MappedFile]) -> dict[str, tuple[str, str]]:
    if ctx.upload_concurrency < 1:
        raise ValueError("upload_concurrency must be positive")
    pending = iter(files)
    uploaded: dict[str, tuple[str, str]] = {}

    async def worker() -> None:
        for mf in pending:
            uploaded[mf.host_path] = await upload_one_file_async(ctx, mf)

    tasks = [asyncio.create_task(worker()) for _ in range(min(ctx.upload_concurrency, len(files)))]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return uploaded


async def stage_copy_async(ctx: AsyncBuildContext, sources: tuple[str, ...], dest: str, chown: str, chmod: str) -> None:
    sub_sources = tuple(ctx.substitute(s) for s in sources)
    sub_dest = ctx.substitute(dest)
    sub_chown = ctx.substitute(chown)
    sub_chmod = ctx.substitute(chmod)

    if not posixpath.isabs(sub_dest):
        sub_dest = posixpath.normpath(posixpath.join(ctx.workdir or "/", sub_dest))

    uid, gid = parse_chown(sub_chown)
    mode_override = parse_chmod(sub_chmod)

    mapped = await asyncio.to_thread(
        ctx.local.collect, sub_sources, sub_dest, uid=uid, gid=gid, mode_override=mode_override
    )
    if not mapped:
        return

    uploaded = await upload_files_async(ctx, mapped)
    for mf in mapped:
        file_uuid, sha256 = uploaded[mf.host_path]
        ctx.pending.append(pending_file_for(mf, file_uuid=file_uuid, sha256=sha256))


async def copy_from_image_async(
    ctx: AsyncBuildContext, from_stage: str, sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> None:
    image = await resolve_stage_image_async(ctx, ctx.substitute(from_stage))
    copy = resolve_image_copy(ctx, image, sources, dest, chown, chmod)
    for path in copy.sources:
        directive = CopyKeyword(from_stage=image, sources=(path,), dest=copy.dest, chown=copy.chown, chmod=copy.chmod)
        chain = ctx.chain(directive.serialize())
        branch = f"layer:{chain}"
        if await ctx.try_cache_hit(branch) is not None:
            ctx.parent_hash = chain
            ctx.pending.clear()
            continue
        source = await export_source_async(ctx, image, path)
        if not source.is_dir:
            stage_image_file(ctx, source, path, copy)
            continue
        archive = UploadedArchive(source.uuid, posixpath.normpath(copy.dest))
        await apply_copy_layer_async(ctx, archive, directory_overrides(source, copy), branch=branch)
        ctx.parent_hash = chain
        ctx.pending.clear()
