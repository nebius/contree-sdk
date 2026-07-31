from __future__ import annotations

from asyncio import Queue, iscoroutinefunction, to_thread
from codecs import getincrementaldecoder
from functools import partial
from io import IOBase, TextIOBase

from contree_sdk._internals.io.typing import AsyncWritable, Writable


EOF = object()


class WriterToQueue:
    def __init__(self, queue: Queue):
        self._queue = queue

    async def write(self, data: bytes):
        if data:
            self._queue.put_nowait(data)

    async def finalize(self):
        self._queue.put_nowait(EOF)


class WriterWrapper:
    def __init__(self, writer: Writable | AsyncWritable):
        self._writer = writer
        write = writer.write
        self._write = write if iscoroutinefunction(write) else partial(to_thread, write)
        self._prepared = False
        self._decoder = None

    async def _prepare(self):
        if self._prepared:
            return
        if await self._is_writer_text():
            self._decoder = getincrementaldecoder("utf-8")(errors="replace")
        self._prepared = True

    async def _is_writer_text(self):
        if isinstance(self._writer, TextIOBase):
            return True
        if isinstance(self._writer, IOBase):
            return False
        try:
            await self._write(b"")
        except TypeError:
            return True
        else:
            return False

    async def write(self, data: bytes):
        await self._prepare()
        if self._decoder is not None:
            return await self._write(self._decoder.decode(data))
        return await self._write(data)

    async def finalize(self):
        if self._decoder is not None and (tail := self._decoder.decode(b"", final=True)):
            await self._write(tail)
        if isinstance(self._writer, WriterToQueue):
            await self._writer.finalize()
