_shell_command = 'cat - ; echo "this is stdout" ; echo "this is stderr" 1>&2'
_stdin = "my input\n"
_stdout = _stdin + "this is stdout\n"
_stderr = "this is stderr\n"


async def test_session_run(session):
    await session.run(shell=_shell_command, stdin=_stdin)

    assert session.stdout == _stdout
    assert session.stderr == _stderr
    assert session.exit_code == 0


def test_session_run_s(session_s):
    session_s.run(shell=_shell_command, stdin=_stdin).wait()

    assert session_s.stdout == _stdout
    assert session_s.stderr == _stderr
    assert session_s.exit_code == 0


def test_session_multiple_runs(session_s):
    data = "some data"
    session_s.run(shell="cat - > /file.txt", stdin=data, disposable=False).wait()
    session_s.run(shell="echo some other step", stdin=data, disposable=False).wait()
    assert session_s.stdout == "some other step\n"
    assert session_s.exit_code == 0
    session_s.run(shell="cat /file.txt", stdin=data).wait()
    assert session_s.stdout == data
    assert session_s.exit_code == 0
