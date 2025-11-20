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


def test_basic_run_s(image_s):
    result = image_s.run(shell=_shell_command, stdin=_stdin).wait()
    assert isinstance(result, ContreeImageSync)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0
