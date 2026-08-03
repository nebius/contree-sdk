from asyncio import Queue, create_task, sleep, wait_for
from io import BytesIO, StringIO
from threading import get_ident

import pytest

from contree_sdk._internals.io.writer_wrapper import EOF, WriterToQueue, WriterWrapper


class _TextSink:
    def __init__(self):
        self.parts: list[str] = []

    def write(self, data: str):
        self.parts.append("" + data)


class _AsyncSink:
    def __init__(self):
        self.parts: list[bytes] = []

    async def write(self, data: bytes):
        self.parts.append(data)


class _ThreadRecordingQueue(Queue):
    def __init__(self):
        super().__init__()
        self.put_thread_ids: list[int] = []

    def put_nowait(self, item):
        self.put_thread_ids.append(get_ident())
        return super().put_nowait(item)


async def test_bytes_writer_gets_raw_bytes():
    buffer = BytesIO()
    wrapper = WriterWrapper(buffer)

    await wrapper.write(b"data")
    await wrapper.finalize()

    assert buffer.getvalue() == b"data"


async def test_text_writer_gets_decoded_str():
    buffer = StringIO()
    wrapper = WriterWrapper(buffer)

    await wrapper.write("Привет".encode())
    await wrapper.finalize()

    assert buffer.getvalue() == "Привет"


async def test_text_writer_decodes_incrementally():
    buffer = StringIO()
    wrapper = WriterWrapper(buffer)

    encoded = "П".encode()
    await wrapper.write(encoded[:1])
    await wrapper.write(encoded[1:])
    await wrapper.finalize()

    assert buffer.getvalue() == "П"


async def test_finalize_flushes_decoder_tail():
    buffer = StringIO()
    wrapper = WriterWrapper(buffer)

    await wrapper.write("П".encode()[:1])
    await wrapper.finalize()

    assert buffer.getvalue() == "�"


async def test_custom_text_writer_sniffed_by_probe():
    sink = _TextSink()
    wrapper = WriterWrapper(sink)

    await wrapper.write(b"data")

    assert "data" in sink.parts


async def test_async_writer_awaited():
    sink = _AsyncSink()
    wrapper = WriterWrapper(sink)

    await wrapper.write(b"data")

    assert b"data" in sink.parts


class _FlushSink:
    def __init__(self):
        self.flushed = False

    def write(self, data: bytes):
        pass

    def flush(self):
        self.flushed = True


class _AsyncFlushSink:
    def __init__(self):
        self.flushed = False

    async def write(self, data: bytes):
        pass

    async def flush(self):
        self.flushed = True


@pytest.mark.parametrize("sink_class", [_FlushSink, _AsyncFlushSink])
async def test_finalize_flushes_writer(sink_class):
    sink = sink_class()
    wrapper = WriterWrapper(sink)

    await wrapper.write(b"data")
    await wrapper.finalize()

    assert sink.flushed


async def test_writer_to_queue_skips_empty_and_finalizes_with_eof():
    queue = Queue()
    writer = WriterToQueue(queue=queue)

    await writer.write(b"")
    await writer.write(b"data")
    await writer.finalize()

    assert queue.get_nowait() == b"data"
    assert queue.get_nowait() is EOF


async def test_writer_to_queue_delivers_to_already_waiting_consumer_on_event_loop_thread():
    queue = _ThreadRecordingQueue()
    wrapper = WriterWrapper(WriterToQueue(queue=queue))
    consumer = create_task(queue.get())
    await sleep(0)

    assert not consumer.done()

    await wrapper.write(b"delayed")

    assert await wait_for(consumer, timeout=1) == b"delayed"
    assert queue.put_thread_ids == [get_ident()]


async def test_finalize_sends_eof_through_wrapper():
    queue = Queue()
    wrapper = WriterWrapper(WriterToQueue(queue=queue))

    await wrapper.write(b"data")
    await wrapper.finalize()

    assert queue.get_nowait() == b"data"
    assert queue.get_nowait() is EOF
