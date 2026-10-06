"""Controlled input delivery with the real SDK lifecycle and testing transport."""

from contree_client.models import InstanceSpawnResponse, StreamRepr

from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event


class StdinClient(LiveClient):
    def __init__(self):
        super().__init__()
        self.ready = True
        self.finish_on_eof = True
        self.write_error: Exception | None = None
        self.received = bytearray()
        self.auto_exit = False

    def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        response = super().spawn_instance(command, image, **kwargs)
        if self.ready:
            self.streams[response.uuid].put(event("spawn"))
        return response

    def operation_subprocess_create(self, operation_id: str, command: str, **kwargs) -> int:
        spid = super().operation_subprocess_create(operation_id, command, **kwargs)
        self.streams[operation_id].put(event("spawn", spid))
        return spid

    def operation_subprocess_stdin(self, operation_id: str, spid: int, value: str, **kwargs) -> None:
        self.record_call("operation_subprocess_stdin", (operation_id, spid, value), kwargs)
        if self.write_error is not None:
            raise self.write_error
        self.received.extend(StreamRepr(value=value, encoding=kwargs["encoding"]).as_bytes())
        if kwargs["close"] and self.finish_on_eof:
            self.streams[operation_id].put(event("exit", spid))
            if spid == 1:
                self.streams[operation_id].put(event("completion"))


class AsyncStdinClient(LiveAsyncClient):
    def __init__(self):
        super().__init__()
        self.ready = True
        self.finish_on_eof = True
        self.write_error: Exception | None = None
        self.received = bytearray()
        self.auto_exit = False

    async def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        response = await super().spawn_instance(command, image, **kwargs)
        if self.ready:
            await self.streams[response.uuid].put(event("spawn"))
        return response

    async def operation_subprocess_create(self, operation_id: str, command: str, **kwargs) -> int:
        spid = await super().operation_subprocess_create(operation_id, command, **kwargs)
        await self.streams[operation_id].put(event("spawn", spid))
        return spid

    async def operation_subprocess_stdin(self, operation_id: str, spid: int, value: str, **kwargs) -> None:
        self.record_call("operation_subprocess_stdin", (operation_id, spid, value), kwargs)
        if self.write_error is not None:
            raise self.write_error
        self.received.extend(StreamRepr(value=value, encoding=kwargs["encoding"]).as_bytes())
        if kwargs["close"] and self.finish_on_eof:
            await self.streams[operation_id].put(event("exit", spid))
            if spid == 1:
                await self.streams[operation_id].put(event("completion"))
