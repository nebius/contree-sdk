"""Run two commands through a sandbox configured from ENV or an INI profile."""

from contree_sdk import create_sync_sandbox_session


def main() -> None:
    with create_sync_sandbox_session(image="tag:alpine:latest") as session:
        session.run(shell="echo 'Hello from ConTree!' > /message.txt")
        result = session.run("cat", args=["/message.txt"])
        print(result.stdout)


if __name__ == "__main__":
    main()


def test_sandbox(sandbox_api, capsys):
    import runpy

    runpy.run_path(__file__, run_name="__main__")
    client = sandbox_api.sync
    assert len(client.calls_for("spawn_instance")) == 1
    calls = client.calls_for("operation_subprocess_create")
    assert calls[0].args[1] == "echo 'Hello from ConTree!' > /message.txt"
    assert calls[1].args[1] == "cat"
    assert calls[1].kwargs["args"] == ["/message.txt"]
    assert len(client.calls_for("operation_subprocess_kill")) == 1
    assert capsys.readouterr().out == "Hello from ConTree!\n\n"
