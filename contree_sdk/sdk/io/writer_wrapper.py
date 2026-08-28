from __future__ import annotations

from asyncio import Queue, QueueEmpty, to_thread
from codecs import getincrementaldecoder
from contextlib import suppress
from functools import partial
from inspect import iscoroutinefunction
from io import IOBase, TextIOBase

from contree_sdk.sdk.io.typing import AsyncWritable, Writable


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

    async def write(self, data: bytes) -> None:
        await self._prepare()
        if self._decoder is not None:
            await self._write(self._decoder.decode(data))
        else:
            await self._write(data)

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


def writer_is_text(writer: Writable) -> bool:
    if isinstance(writer, TextIOBase):
        return True
    if isinstance(writer, IOBase):
        return False
    try:
        writer.write(b"")
    except TypeError:
        return True
    else:
        return False


class SyncWriterWrapper:
    """Blocking analog of :class:`WriterWrapper` for the sync waiter.

    No fan-out, no threads: a sync image-like object only ever has one
    consumer of the event stream at a time, so writes happen inline.
    """

    def __init__(self, writer: Writable):
        self.writer = writer
        self.decoder = getincrementaldecoder("utf-8")(errors="replace") if writer_is_text(writer) else None

    def write(self, data: bytes) -> None:
        if self.decoder is not None:
            self.writer.write(self.decoder.decode(data))
        else:
            self.writer.write(data)

    def finalize(self) -> None:
        if self.decoder is not None and (tail := self.decoder.decode(b"", final=True)):
            self.writer.write(tail)
        flush = getattr(self.writer, "flush", None)
        if flush is not None:
            flush()
