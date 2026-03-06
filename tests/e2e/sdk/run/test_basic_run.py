from datetime import timedelta
from io import IOBase, StringIO
from pathlib import Path
from subprocess import PIPE

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


async def test_apply_files(image: ContreeImage, test_txt_path: Path):
    result = await image.apply_files(test_txt_path)
    assert isinstance(result, ContreeImage)
    verified = await result.run(shell=f"cat /{test_txt_path.name} | grep line")
    assert verified.stdout == "second line\nlast line\n"


def test_apply_files_s(image_s: ContreeImageSync, test_txt_path: Path):
    result = image_s.apply_files(test_txt_path)
    assert isinstance(result, ContreeImageSync)
    verified = result.run(shell=f"cat /{test_txt_path.name} | grep line").wait()
    assert verified.stdout == "second line\nlast line\n"


_shell_command = 'cat - ; echo "this is stdout" ; echo "this is stderr" 1>&2'
_stdin = "my input\n"
_stdout = _stdin + "this is stdout\n"
_stderr = "this is stderr\n"


async def test_basic_run(image):
    image_repr = repr(image)
    assert repr(_stdout[:10])[:-1] not in image_repr

    result = await image.run(shell=_shell_command, stdin=_stdin)
    assert isinstance(result, ContreeImage)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0

    image_repr = repr(result)
    assert "0" in image_repr
    assert repr(_stdout[:10])[:-1] in image_repr
    assert repr(_stderr[:10])[:-1] in image_repr

    elapsed = result.elapsed
    assert isinstance(elapsed, timedelta)
    assert elapsed.total_seconds() > 0


def test_basic_run_s(image_s):
    image_repr = repr(image_s)
    assert repr(_stdout[:10])[:-1] not in image_repr

    result = image_s.run(shell=_shell_command, stdin=_stdin).wait()
    assert isinstance(result, ContreeImageSync)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0

    image_repr = repr(result)
    assert "0" in image_repr
    assert repr(_stdout[:10])[:-1] in image_repr
    assert repr(_stderr[:10])[:-1] in image_repr

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


def test_run_file_io_s(image_s, tmp_file, test_txt_path):
    result = image_s.run(shell="cat - | grep line", stdin=test_txt_path, stdout=str(tmp_file)).wait()
    assert isinstance(result, ContreeImageSync)

    assert tmp_file.read_bytes() == b"second line\nlast line\n"
    assert result.exit_code == 0


_truncate_at = 50
_long_output_command = "dd if=/dev/urandom bs=100 count=1 2>/dev/null | base64"


async def test_run_truncated_output(image):
    result = await image.run(shell=_long_output_command, truncate_output_at=_truncate_at)
    assert len(result.stdout) == _truncate_at


RANDOM_INT_COMMAND = "od -An -N2 -tu2 /dev/urandom"


async def test_preconfigured_run(image):
    preconfigured_run = image.run(shell=RANDOM_INT_COMMAND)

    result1 = await preconfigured_run
    result2 = await preconfigured_run
    result3 = await preconfigured_run
    results = [result1, result2, result3]

    numbers = {int(result.stdout) for result in results}
    assert len(numbers) == 3
