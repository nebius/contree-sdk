from datetime import timedelta
from io import IOBase, StringIO
from pathlib import Path
from subprocess import PIPE
from tempfile import NamedTemporaryFile

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


_shell_command = 'cat - ; echo "this is stdout" ; echo "this is stderr" 1>&2'
_stdin = "my input\n"
_stdout = _stdin + "this is stdout\n"
_stderr = "this is stderr\n"


async def test_basic_run(image):
    result = await image.run(shell=_shell_command, stdin=_stdin)
    assert isinstance(result, ContreeImage)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0

    elapsed = result.elapsed
    assert isinstance(elapsed, timedelta)
    assert elapsed.total_seconds() > 0


def test_basic_run_s(image_s):
    result = image_s.run(shell=_shell_command, stdin=_stdin).wait()
    assert isinstance(result, ContreeImageSync)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0

    elapsed = result.elapsed
    assert isinstance(elapsed, timedelta)
    assert elapsed.total_seconds() > 0


def test_run_with_files_s(image_s, test_txt_path: Path):
    result = image_s.run(shell=f"cat /{test_txt_path.name} | grep line", files=[test_txt_path]).wait()
    assert isinstance(result, ContreeImageSync)
    assert result.stdout == "second line\nlast line\n"


def test_run_io_input_s(image_s):
    io_obj = StringIO(_stdin)

    result = image_s.run(shell=_shell_command, stdin=io_obj, stderr=bytes).wait()
    assert isinstance(result, ContreeImageSync)

    assert result.stdout == _stdout
    assert result.stderr == _stderr.encode()
    assert result.exit_code == 0


def test_run_io_output_s(image_s):
    stdout_io = StringIO()
    result = image_s.run(shell=_shell_command, stdin=_stdin, stdout=stdout_io, stderr=PIPE).wait()

    assert isinstance(result.stderr, IOBase)
    assert result.stderr.read() == _stderr.encode()

    assert result.stdout == stdout_io
    assert stdout_io.getvalue() == _stdout


def test_run_file_io_s(image_s, test_txt_path):
    with NamedTemporaryFile() as f:
        result = image_s.run(shell="cat - | grep line", stdin=test_txt_path, stdout=f.name).wait()
        assert isinstance(result, ContreeImageSync)

        assert f.read() == b"second line\nlast line\n"
        assert result.exit_code == 0
