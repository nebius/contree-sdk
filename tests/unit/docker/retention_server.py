"""Stateful remote objects for offline retention tests of the real Docker builder."""

import hashlib
import inspect
import io
import posixpath
import tarfile
from collections.abc import Callable
from typing import Any

from contree_client.exceptions import NotFoundError
from contree_client.models import DirectoryList, FileResponse

from tests.unit.docker.copy_clients import CopyAsyncClient, CopyClient, source_item


class RetentionServer:
    def __init__(self):
        self.images: dict[str, dict[str, bytes]] = {"base": {}}
        self.files: dict[str, bytes] = {}
        self.operations: dict[str, dict[str, bytes]] = {}
        self.upload_sequence = 0
        self.missing_requests: list[str] = []

    def image(self, image: str) -> dict[str, bytes]:
        if image not in self.images:
            self.missing_requests.append(image)
            raise NotFoundError(404, f"retained image expired: {image}")
        return self.images[image]

    def file(self, uuid: str) -> bytes:
        if uuid not in self.files:
            self.missing_requests.append(uuid)
            raise NotFoundError(404, f"retained file expired: {uuid}")
        return self.files[uuid]

    def ensure_file(self, content: Any, **kwargs: Any) -> FileResponse:
        data = content.read()
        sha = hashlib.sha256(data).hexdigest()
        for uuid, existing in self.files.items():
            if data == existing:
                return FileResponse(uuid=uuid, sha256=sha, size=len(data))
        self.upload_sequence += 1
        uuid = f"upload-{self.upload_sequence}"
        self.files[uuid] = data
        return FileResponse(uuid=uuid, sha256=sha, size=len(data))

    def check_file_exists(self, sha256: str) -> bool:
        return any(hashlib.sha256(data).hexdigest() == sha256 for data in self.files.values())

    def check_image_archive(self, image: str, path: str) -> bool:
        return image in self.images

    def inspect_image_list(self, image: str, path: str) -> DirectoryList:
        prefix = path.rstrip("/") + "/"
        entries: dict[str, bool] = {}
        for filename in self.image(image):
            if filename.startswith(prefix):
                relative = filename[len(prefix) :]
                name, separator, _ = relative.partition("/")
                entries[name] = bool(separator)
        return DirectoryList(path=path, files=[source_item(name, is_dir=is_dir) for name, is_dir in entries.items()])

    def inspect_image_download_stream(self, image: str, path: str) -> list[bytes]:
        return [self.image(image)[path]]

    def inspect_image_archive(self, image: str, path: str, **kwargs: Any) -> list[bytes]:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            root = tarfile.TarInfo(".")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            prefix = path.rstrip("/") + "/"
            for filename, data in sorted(self.image(image).items()):
                if filename.startswith(prefix):
                    member = tarfile.TarInfo(filename[len(prefix) :])
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
        return [buffer.getvalue()]

    def apply_instance_file(self, operation: str, file: str, path: str, **kwargs: Any) -> None:
        with tarfile.open(fileobj=io.BytesIO(self.file(file))) as archive:
            for member in archive:
                if member.isfile():
                    content = archive.extractfile(member)
                    if content is None:
                        raise ValueError("archive member has no content")
                    self.operations[operation][posixpath.join(path, member.name)] = content.read()

    def start(self, command: str, image: str, kwargs: dict[str, Any]) -> dict[str, bytes]:
        snapshot = dict(self.image(image))
        files = kwargs.get("files")
        if isinstance(files, dict):
            for path, spec in files.items():
                snapshot[path] = self.file(spec.uuid)
        args = kwargs.get("args")
        script = args[-1] if isinstance(args, list) and args else command
        if script == "compile":
            snapshot["/out/tool"] = b"compiled:" + snapshot["/seed"]
        elif script == "source-extra":
            snapshot["/out/extra"] = b"extra"
        elif script == "finish":
            snapshot["/result"] = snapshot.get("/app/tool", b"") + snapshot.get("/bin/tool", b"")
        return snapshot

    def install(self, client: CopyClient | CopyAsyncClient, monkeypatch: Any) -> None:
        """Replace remote I/O and retain the SDK operation lifecycle and Store."""

        def recorded(name: str, method: Callable[..., Any]) -> Callable[..., Any]:
            def invoke(*args: Any, **kwargs: Any) -> Any:
                client.record_call(name, args, kwargs)
                return method(*args, **kwargs)

            return invoke

        def asynchronous(method: Callable[..., Any]) -> Callable[..., Any]:
            async def invoke(*args: Any, **kwargs: Any) -> Any:
                return method(*args, **kwargs)

            return invoke

        def stream(method: Callable[..., Any]) -> Callable[..., Any]:
            async def invoke(*args: Any, **kwargs: Any) -> Any:
                for chunk in method(*args, **kwargs):
                    yield chunk

            return invoke

        for name in (
            "ensure_file",
            "check_file_exists",
            "check_image_archive",
            "inspect_image_list",
            "inspect_image_download_stream",
            "inspect_image_archive",
            "apply_instance_file",
        ):
            method = recorded(name, getattr(self, name))
            if isinstance(client, CopyAsyncClient):
                method = (
                    stream(method) if inspect.isasyncgenfunction(getattr(type(client), name)) else asynchronous(method)
                )
            monkeypatch.setattr(client, name, method)

        if isinstance(client, CopyAsyncClient):
            spawn_async_method, status_async_method = client.spawn_instance, client.get_operation_status

            async def spawn_async(command: str, image: str, **kwargs: Any) -> Any:
                snapshot = self.start(command, image, kwargs)
                response = await spawn_async_method(command, image, **kwargs)
                self.operations[str(response.uuid)] = snapshot
                return response

            async def status_async(operation: str, **kwargs: Any) -> Any:
                response = await status_async_method(operation, **kwargs)
                self.images[str(response.result_image_uuid)] = dict(self.operations[operation])
                return response

            monkeypatch.setattr(client, "spawn_instance", spawn_async)
            monkeypatch.setattr(client, "get_operation_status", status_async)
        else:
            spawn, status = client.spawn_instance, client.get_operation_status

            def spawn_sync(command: str, image: str, **kwargs: Any) -> Any:
                snapshot = self.start(command, image, kwargs)
                response = spawn(command, image, **kwargs)
                self.operations[str(response.uuid)] = snapshot
                return response

            def status_sync(operation: str, **kwargs: Any) -> Any:
                response = status(operation, **kwargs)
                self.images[str(response.result_image_uuid)] = dict(self.operations[operation])
                return response

            monkeypatch.setattr(client, "spawn_instance", spawn_sync)
            monkeypatch.setattr(client, "get_operation_status", status_sync)
