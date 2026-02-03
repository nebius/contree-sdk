from io import BytesIO, StringIO
from pathlib import Path
from subprocess import PIPE

import pytest

from contree_sdk.utils.io_wrap import IOMode, get_io_by_obj


@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    return tmp_path / "tmp.bin"


def test_str_input():
    string = "test data"
    io_obj = get_io_by_obj(string, IOMode.read)
    assert io_obj is not None
    assert io_obj.read() == string


def test_str_io_input():
    string = "test data"
    io_obj = get_io_by_obj(StringIO(string), IOMode.read)
    assert io_obj is not None
    assert io_obj.read() == string


def test_bytes_input():
    data = b"test data"
    io_obj = get_io_by_obj(data, IOMode.read)
    assert io_obj is not None
    assert io_obj.read() == data


def test_bytes_io_input():
    data = b"test data"
    io_obj = get_io_by_obj(BytesIO(data), IOMode.read)
    assert io_obj is not None
    assert io_obj.read() == data


def test_path_input(test_txt_path: Path):
    io_obj = get_io_by_obj(test_txt_path, IOMode.read)
    assert io_obj is not None
    assert io_obj.read() == test_txt_path.read_bytes()


def test_pipe_input():
    data = b"test data"
    io_obj = get_io_by_obj(PIPE, IOMode.read)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.close()
    assert io_obj.read() == data


def test_path_output(tmp_file: Path):
    data = b"test data"
    io_obj = get_io_by_obj(tmp_file, IOMode.write)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.flush()
    assert tmp_file.read_bytes() == data


def test_str_path_output(tmp_file: Path):
    data = b"test data"
    io_obj = get_io_by_obj(str(tmp_file), IOMode.write)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.flush()
    assert tmp_file.read_bytes() == data


def test_bytes_io_output():
    data = b"test data"
    obj = BytesIO()
    io_obj = get_io_by_obj(obj, IOMode.write)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.flush()
    assert obj.getvalue() == data


def test_str_io_output():
    data = "test data"
    obj = StringIO()
    io_obj = get_io_by_obj(obj, IOMode.write)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.flush()
    assert obj.getvalue() == data


def test_pipe_output():
    data = b"test data"
    io_obj = get_io_by_obj(PIPE, IOMode.write)
    assert io_obj is not None
    io_obj.write(data)
    io_obj.close()
    assert io_obj.read() == data
