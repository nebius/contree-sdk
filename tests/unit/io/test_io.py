from io import BytesIO, StringIO
from pathlib import Path
from subprocess import PIPE

from contree_sdk._internals.io.wiring import finalize_output, get_output_obj, read_input
from contree_sdk.utils.io import PipeIO


async def test_none_input():
    assert await read_input(None) == ""


async def test_str_input():
    string = "test data"
    assert await read_input(string) == string


async def test_str_io_input():
    string = "test data"
    assert await read_input(StringIO(string)) == string


async def test_bytes_input():
    data = b"test data"
    assert await read_input(data) == data


async def test_bytes_io_input():
    data = b"test data"
    assert await read_input(BytesIO(data)) == data


async def test_path_input(test_txt_path: Path):
    assert await read_input(test_txt_path) == test_txt_path.read_bytes()


def test_none_output():
    assert get_output_obj(None) is None
    assert finalize_output(None, None, b"test data") is None


def test_str_request_output():
    assert get_output_obj(str) is None
    assert finalize_output(str, None, b"test data") == "test data"


def test_bytes_request_output():
    assert get_output_obj(bytes) is None
    assert finalize_output(bytes, None, b"test data") == b"test data"


def test_path_output(tmp_file: Path):
    data = b"test data"
    io_obj = get_output_obj(tmp_file)
    assert io_obj is not None
    io_obj.write(data)
    assert finalize_output(tmp_file, io_obj, data) == tmp_file
    assert tmp_file.read_bytes() == data


def test_str_path_output(tmp_file: Path):
    data = b"test data"
    io_obj = get_output_obj(str(tmp_file))
    assert io_obj is not None
    io_obj.write(data)
    assert finalize_output(str(tmp_file), io_obj, data) == tmp_file
    assert tmp_file.read_bytes() == data


def test_bytes_io_output():
    data = b"test data"
    obj = BytesIO()
    io_obj = get_output_obj(obj)
    assert io_obj is obj
    io_obj.write(data)
    assert finalize_output(obj, io_obj, data) is obj
    assert obj.getvalue() == data


def test_str_io_output():
    data = "test data"
    obj = StringIO()
    io_obj = get_output_obj(obj)
    assert io_obj is obj
    io_obj.write(data)
    assert finalize_output(obj, io_obj, data.encode()) is obj
    assert obj.getvalue() == data


def test_pipe_output():
    data = b"test data"
    io_obj = get_output_obj(PIPE)
    assert isinstance(io_obj, PipeIO)
    io_obj.write(data)
    finalized = finalize_output(PIPE, io_obj, data)
    assert finalized is io_obj
    assert io_obj.read() == data
