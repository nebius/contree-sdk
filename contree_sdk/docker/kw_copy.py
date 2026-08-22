"""`COPY [--from=...] [--chown=...] [--chmod=...] SRC... DEST`.

Local sources are uploaded from the build context and attached to the next
RUN. `--from=<stage|index|image>` sources are exported from the referenced
image as a tar archive, uploaded as a single file and unpacked by an
extraction RUN inside the sandbox, so ownership, modes and symlinks survive
natively.
"""

from __future__ import annotations

import asyncio
import json
import posixpath
import shlex
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, ClassVar, TypedDict

from contree_client.exceptions import NotFoundError
from contree_client.models import File, FileResponse

from contree_sdk.exceptions import DockerBuildError

from .context import AsyncBuildContext, BuildContext, PendingFile, resolve_stage_ref
from .keyword import DockerKeyword
from .kw_from import resolve_or_import, resolve_or_import_async
from .kw_run import RunKeyword
from .local_context import MappedFile


SPOOL_MAX_MEMORY = 8 * 1024 * 1024
MAX_CACHE_AGE = 90 * 24 * 3600  # 90 days
MIN_COPY_LIKE_ARGS = 2


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


# -- local file cache (host_path + inode + mtime + size -> uploaded uuid) --


def abs_host_path(host_path: str) -> str:
    return str(Path(host_path).resolve())


def local_file_cache_key(host_path: str) -> str:
    abs_path = Path(abs_host_path(host_path))
    stat = abs_path.stat()
    fingerprint = f"{abs_path}:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}"
    digest = uuid.uuid5(uuid.NAMESPACE_URL, fingerprint)
    return f"local_file:{digest}"


def cached_local_uuid(ctx: BuildContext, mf: MappedFile) -> str | None:
    cached = ctx.cache.get(local_file_cache_key(mf.host_path))
    if isinstance(cached, dict) and cached.get("uuid"):
        age = time.time() - cached.get("uploaded_at", 0)
        if age < MAX_CACHE_AGE:
            return str(cached["uuid"])
    return None


def record_local_uuid(ctx: BuildContext, mf: MappedFile, file_uuid: str) -> None:
    ctx.cache.set(
        local_file_cache_key(mf.host_path),
        {"uuid": file_uuid, "uploaded_at": time.time(), "local_path": abs_host_path(mf.host_path)},
    )


def upload_files(ctx: BuildContext, files: list[MappedFile]) -> dict[str, str]:
    # upload host files, returning host_path -> file_uuid
    uploaded: dict[str, str] = {}
    for mf in files:
        cached = cached_local_uuid(ctx, mf)
        if cached:
            uploaded[mf.host_path] = cached
            record_local_uuid(ctx, mf, cached)
            continue
        with Path(mf.host_path).open("rb") as handle:
            stored = ctx.client.ensure_file(handle)
        file_uuid = str(stored.uuid)
        uploaded[mf.host_path] = file_uuid
        record_local_uuid(ctx, mf, file_uuid)
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
        ctx.pending.append(pending_file_for(mf, file_uuid=uploaded[mf.host_path], sha256=mf.sha256()))


def resolve_stage_image(ctx: BuildContext, ref: str) -> str:
    # map a `--from` reference (stage alias/index, or external image) to an image UUID
    local = resolve_stage_ref(ctx, ref)
    if local is not None:
        return local
    return resolve_or_import(ctx, ref)


def fetch_archive(ctx: BuildContext, stage_ref: str, image_uuid: str, src: str, buffer: IO[bytes]) -> None:
    # fill `buffer` with the tar export of `src` from `image_uuid`
    try:
        for chunk in ctx.client.inspect_image_archive(image_uuid, src, compressed=False):
            buffer.write(chunk)
    except NotFoundError:
        raise DockerBuildError(f"COPY --from={stage_ref}: {src} not found in {image_uuid}") from None
    buffer.seek(0)


def archive_root(buffer: IO[bytes], src: str) -> tuple[str, bool]:
    # peek the buffered tar: its root member name and directory-ness
    with tarfile.open(fileobj=buffer, mode="r:") as tar:
        member = tar.next()
        if member is None:
            raise ValueError(f"COPY --from: empty archive for {src}")
        root = member.name.split("/", 1)[0]
        is_dir = member.isdir() or member.name.rstrip("/") != root
    buffer.seek(0)
    return root, is_dir


@dataclass(frozen=True)
class ExtractSpec:
    sub_dest: str
    dest_is_dir: bool
    sub_chown: str
    mode_override: int | None
    uid: int
    gid: int


def build_extract_spec(
    ctx: BuildContext | AsyncBuildContext, sub_sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> ExtractSpec:
    sub_dest = ctx.substitute(dest)
    dest_is_dir = sub_dest.endswith("/") or len(sub_sources) > 1
    if not posixpath.isabs(sub_dest):
        sub_dest = posixpath.join(ctx.workdir or "/", sub_dest)
    sub_dest = posixpath.normpath(sub_dest)

    sub_chown = ctx.substitute(chown)
    uid, gid = parse_chown(sub_chown)
    mode_override = parse_chmod(ctx.substitute(chmod))
    return ExtractSpec(
        sub_dest=sub_dest, dest_is_dir=dest_is_dir, sub_chown=sub_chown, mode_override=mode_override, uid=uid, gid=gid
    )


def copy_from_image(
    ctx: BuildContext, from_stage: str, sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> None:
    """Stage a `COPY --from` directive as one extraction layer."""
    stage_ref = ctx.substitute(from_stage)
    image_uuid = resolve_stage_image(ctx, stage_ref)
    scratch_dir = f"/.contree-build-{uuid.uuid4().hex[:8]}"
    sub_sources = tuple(ctx.substitute(s) for s in sources)
    spec = build_extract_spec(ctx, sub_sources, dest, chown, chmod)

    script: list[str] = []
    for index, raw_src in enumerate(sub_sources):
        export_source(ctx, script, index, raw_src, scratch_dir, stage_ref, image_uuid, spec)

    script.append(f"rm -rf {shlex.quote(scratch_dir)}")
    command = " && ".join(script)

    saved_user = ctx.user
    ctx.user = ""
    try:
        RunKeyword(parts=(command,), shell_form=True).execute(ctx)
    finally:
        ctx.user = saved_user


def export_source(
    ctx: BuildContext,
    script: list[str],
    index: int,
    raw_src: str,
    scratch_dir: str,
    stage_ref: str,
    image_uuid: str,
    spec: ExtractSpec,
) -> None:
    src = posixpath.normpath(posixpath.join("/", raw_src))
    tar_path = f"{scratch_dir}/copy-{index}.tar"
    extract_dir = f"{scratch_dir}/extract-{index}"

    with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY) as buffer:
        fetch_archive(ctx, stage_ref, image_uuid, src, buffer)
        root, is_dir = archive_root(buffer, src)
        stored = ctx.client.ensure_file(buffer)

    ctx.pending.append(pending_file_for_tar(tar_path, stored))
    append_extract_script(
        script, tar_path=tar_path, extract_dir=extract_dir, root=root, is_dir=is_dir, src=src, spec=spec
    )


def append_extract_script(
    script: list[str], *, tar_path: str, extract_dir: str, root: str, is_dir: bool, src: str, spec: ExtractSpec
) -> None:
    unpacked = f"{extract_dir}/{root}"
    script.append(f"mkdir -p {shlex.quote(extract_dir)}")
    script.append(f"tar -xf {shlex.quote(tar_path)} -C {shlex.quote(extract_dir)}")
    if spec.sub_chown:
        script.append(f"chown -R {spec.uid}:{spec.gid} {shlex.quote(unpacked)}")
    if spec.mode_override is not None:
        flag = "-R " if is_dir else ""
        script.append(f"chmod {flag}{spec.mode_override:o} {shlex.quote(unpacked)}")
    if is_dir:
        # Docker copies the CONTENTS of a directory source.
        script.append(f"mkdir -p {shlex.quote(spec.sub_dest)}")
        script.append(f"cp -a {shlex.quote(unpacked)}/. {shlex.quote(spec.sub_dest)}/")
    else:
        target = posixpath.join(spec.sub_dest, posixpath.basename(src)) if spec.dest_is_dir else spec.sub_dest
        script.append(f"mkdir -p {shlex.quote(posixpath.dirname(target) or '/')}")
        script.append(f"mv {shlex.quote(unpacked)} {shlex.quote(target)}")


def pending_file_for_tar(tar_path: str, stored: File | FileResponse) -> PendingFile:
    return PendingFile(
        instance_path=tar_path, file_uuid=str(stored.uuid), sha256=str(stored.sha256), uid=0, gid=0, mode="0600"
    )


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


async def cached_local_uuid_async(ctx: AsyncBuildContext, mf: MappedFile) -> str | None:
    cached = await ctx.cache.get(local_file_cache_key(mf.host_path))
    if isinstance(cached, dict) and cached.get("uuid"):
        age = time.time() - cached.get("uploaded_at", 0)
        if age < MAX_CACHE_AGE:
            return str(cached["uuid"])
    return None


async def record_local_uuid_async(ctx: AsyncBuildContext, mf: MappedFile, file_uuid: str) -> None:
    await ctx.cache.set(
        local_file_cache_key(mf.host_path),
        {"uuid": file_uuid, "uploaded_at": time.time(), "local_path": abs_host_path(mf.host_path)},
    )


async def upload_one_remote_async(ctx: AsyncBuildContext, mf: MappedFile) -> tuple[MappedFile, str]:
    content = await asyncio.to_thread(Path(mf.host_path).read_bytes)
    stored = await ctx.client.ensure_file(content)
    return mf, str(stored.uuid)


async def upload_files_async(ctx: AsyncBuildContext, files: list[MappedFile]) -> dict[str, str]:
    uploaded: dict[str, str] = {}
    pending: list[MappedFile] = []
    for mf in files:
        cached = await cached_local_uuid_async(ctx, mf)
        if cached:
            uploaded[mf.host_path] = cached
            await record_local_uuid_async(ctx, mf, cached)
        else:
            pending.append(mf)

    if not pending:
        return uploaded

    results = await asyncio.gather(*(upload_one_remote_async(ctx, mf) for mf in pending))
    for mf, file_uuid in results:
        uploaded[mf.host_path] = file_uuid
        await record_local_uuid_async(ctx, mf, file_uuid)
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
        sha256 = await asyncio.to_thread(mf.sha256)
        ctx.pending.append(pending_file_for(mf, file_uuid=uploaded[mf.host_path], sha256=sha256))


async def fetch_archive_async(
    ctx: AsyncBuildContext, stage_ref: str, image_uuid: str, src: str, buffer: IO[bytes]
) -> None:
    try:
        async for chunk in ctx.client.inspect_image_archive(image_uuid, src, compressed=False):
            buffer.write(chunk)
    except NotFoundError:
        raise DockerBuildError(f"COPY --from={stage_ref}: {src} not found in {image_uuid}") from None
    buffer.seek(0)


async def copy_from_image_async(
    ctx: AsyncBuildContext, from_stage: str, sources: tuple[str, ...], dest: str, chown: str, chmod: str
) -> None:
    stage_ref = ctx.substitute(from_stage)
    image_uuid = await resolve_stage_image_async(ctx, stage_ref)
    scratch_dir = f"/.contree-build-{uuid.uuid4().hex[:8]}"
    sub_sources = tuple(ctx.substitute(s) for s in sources)
    spec = build_extract_spec(ctx, sub_sources, dest, chown, chmod)

    script: list[str] = []
    for index, raw_src in enumerate(sub_sources):
        await export_source_async(ctx, script, index, raw_src, scratch_dir, stage_ref, image_uuid, spec)

    script.append(f"rm -rf {shlex.quote(scratch_dir)}")
    command = " && ".join(script)

    saved_user = ctx.user
    ctx.user = ""
    try:
        await RunKeyword(parts=(command,), shell_form=True).execute_async(ctx)
    finally:
        ctx.user = saved_user


async def export_source_async(
    ctx: AsyncBuildContext,
    script: list[str],
    index: int,
    raw_src: str,
    scratch_dir: str,
    stage_ref: str,
    image_uuid: str,
    spec: ExtractSpec,
) -> None:
    src = posixpath.normpath(posixpath.join("/", raw_src))
    tar_path = f"{scratch_dir}/copy-{index}.tar"
    extract_dir = f"{scratch_dir}/extract-{index}"

    with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY) as buffer:
        await fetch_archive_async(ctx, stage_ref, image_uuid, src, buffer)
        root, is_dir = archive_root(buffer, src)
        stored = await ctx.client.ensure_file(buffer)

    ctx.pending.append(pending_file_for_tar(tar_path, stored))
    append_extract_script(
        script, tar_path=tar_path, extract_dir=extract_dir, root=root, is_dir=is_dir, src=src, spec=spec
    )
