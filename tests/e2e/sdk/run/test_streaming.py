from asyncio import gather

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


_shell_command = 'cat - ; echo "this is stdout" ; echo "this is stderr" 1>&2'
_stdin = "my input\n"
_stdout = _stdin + "this is stdout\n"
_stderr = "this is stderr\n"


def _joined(chunks, stream_name: str) -> bytes:
    return b"".join(chunk.value for chunk in chunks if chunk.stream_name == stream_name)


async def test_start_then_await(image: ContreeImage):
    started = await image.run(shell=_shell_command, stdin=_stdin).start()

    result = await started

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0


async def test_multiple_awaits_share_result(image: ContreeImage):
    started = await image.run(shell=_shell_command, stdin=_stdin).start()

    first, second = await gather(started, started)

    assert first is second
    assert first.stdout == _stdout


async def test_iterate_run_output(image: ContreeImage):
    started = await image.run(shell=_shell_command, stdin=_stdin).start()

    chunks = [chunk async for chunk in started]

    assert _joined(chunks, "stdout") == _stdout.encode()
    assert _joined(chunks, "stderr") == _stderr.encode()
    assert started.exit_code == 0


def test_iterate_run_output_s(image_s: ContreeImageSync):
    started = image_s.run(shell=_shell_command, stdin=_stdin).start()

    chunks = list(started)

    assert _joined(chunks, "stdout") == _stdout.encode()
    assert _joined(chunks, "stderr") == _stderr.encode()
    assert started.exit_code == 0
