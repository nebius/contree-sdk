from typing import Protocol, TypeVar, runtime_checkable


DataTypeT = TypeVar("DataTypeT", str, bytes)


@runtime_checkable
class Readable(Protocol[DataTypeT]):
    def read(self, size: int = -1, /) -> DataTypeT: ...
    def close(self) -> None: ...


@runtime_checkable
class AsyncReadable(Protocol[DataTypeT]):
    async def read(self, size: int = -1, /) -> DataTypeT: ...
    async def close(self) -> None: ...


@runtime_checkable
class Writable(Protocol[DataTypeT]):
    def write(self, data: DataTypeT, /) -> object: ...


@runtime_checkable
class AsyncWritable(Protocol[DataTypeT]):
    async def write(self, data: DataTypeT, /) -> object: ...
