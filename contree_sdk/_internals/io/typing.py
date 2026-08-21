from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, runtime_checkable


DataTypeT = TypeVar("DataTypeT", str, bytes)


@runtime_checkable
class Readable(Protocol[DataTypeT]):
    def read(self, size: int = -1, /) -> DataTypeT: ...
    def close(self) -> None: ...


@runtime_checkable
class AsyncReadable(Protocol[DataTypeT]):
    async def read(self, size: int = -1, /) -> DataTypeT: ...
    async def close(self) -> None: ...


INPUT_TYPES: TypeAlias = str | bytes | Path | Readable | AsyncReadable
