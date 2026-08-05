from __future__ import annotations

from asyncio import Queue, QueueEmpty, to_thread
from codecs import getincrementaldecoder
from contextlib import suppress
from functools import partial
from inspect import iscoroutinefunction
from io import IOBase, TextIOBase

from contree_sdk._internals.io.typing import AsyncWritable, Writable


EOF = object()


class WriterToQueue:
    def __init__(self, queue: Queue):
        self._queue = queue
        self._closed = False

    async def write(self, data: bytes):
        if data and not self._closed:
            await self._queue.put(data)
            if self._closed:
                with suppress(QueueEmpty):
                    self._queue.get_nowait()

    async def finalize(self):
        if not self._closed:
            await self._queue.put(EOF)

    def close(self) -> None:
        self._closed = True
        try:
            while True:
                self._queue.get_nowait()
        except QueueEmpty:
            pass


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
        flush = getattr(self._writer, "flush", None)
        if flush is None:
            return
        if iscoroutinefunction(flush):
            await flush()
        else:
            await to_thread(flush)
