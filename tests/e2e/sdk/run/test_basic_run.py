from datetime import timedelta
from io import StringIO
from pathlib import Path, PurePosixPath
from subprocess import PIPE

import pytest

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.utils.io import PipeIO
from contree_sdk.utils.models.file import UploadFileSpec


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


async def test_run_with_file_spec_path(image: ContreeImage, test_txt_path: Path):
    result = await image.run(
        shell="cat /data.txt | grep line",
        files=[UploadFileSpec(source=test_txt_path, path=PurePosixPath("/data.txt"))],
    )
    assert isinstance(result, ContreeImage)
    assert result.stdout == "second line\nlast line\n"


def test_run_with_file_spec_path_s(image_s: ContreeImageSync, test_txt_path: Path):
    result = image_s.run(
        shell="cat /data.txt | grep line",
        files=[UploadFileSpec(source=test_txt_path, path=PurePosixPath("/data.txt"))],
    ).wait()
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

    assert isinstance(result.stderr, PipeIO)
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


@pytest.mark.xfail(raises=AssertionError, reason="server does not truncate output yet")
async def test_run_truncated_output(image):
    result = await image.run(shell=_long_output_command, truncate_output_at=_truncate_at)
    assert len(result.stdout) == _truncate_at


async def test_run_preserve_env(image):
    result = await image.run(
        shell="true",
        env={"SDK_PRESERVE_ENV": "ok"},
        preserve_env=True,
        disposable=False,
    )

    verified = await result.run(shell="printenv SDK_PRESERVE_ENV")
    assert verified.stdout.strip() == "ok"


def test_run_preserve_env_s(image_s):
    result = image_s.run(
        shell="true",
        env={"SDK_PRESERVE_ENV_SYNC": "ok"},
        preserve_env=True,
        disposable=False,
    ).wait()

    verified = result.run(shell="printenv SDK_PRESERVE_ENV_SYNC").wait()
    assert verified.stdout.strip() == "ok"


async def test_run_without_preserve_env_does_not_persist_env(image):
    result = await image.run(
        shell="true",
        env={"SDK_GHOST_ENV": "missing"},
        disposable=False,
    )

    verified = await result.run(shell="printenv SDK_GHOST_ENV || true")
    assert verified.stdout.strip() == ""


def test_run_without_preserve_env_does_not_persist_env_s(image_s):
    result = image_s.run(
        shell="true",
        env={"SDK_GHOST_ENV_SYNC": "missing"},
        disposable=False,
    ).wait()

    verified = result.run(shell="printenv SDK_GHOST_ENV_SYNC || true").wait()
    assert verified.stdout.strip() == ""


RANDOM_INT_COMMAND = "od -An -N2 -tu2 /dev/urandom"


async def test_preconfigured_run(image):
    preconfigured_run = image.run(shell=RANDOM_INT_COMMAND)

    result1 = await preconfigured_run
    result2 = await preconfigured_run
    result3 = await preconfigured_run
    results = [result1, result2, result3]

    numbers = {int(result.stdout) for result in results}
    assert len(numbers) == 3
