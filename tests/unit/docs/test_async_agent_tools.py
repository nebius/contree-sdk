"""Exercise real deepagents tools through native asynchronous SDK execution."""

import pytest


@pytest.mark.parametrize(
    ("tool", "args", "outputs", "expected"),
    [
        ("read_file", {"file_path": "/note.txt"}, ['{"content":"hello","encoding":"utf-8"}'], "hello"),
        ("write_file", {"file_path": "/note.txt", "content": "hello"}, ["", ""], "/note.txt"),
        (
            "edit_file",
            {"file_path": "/note.txt", "old_string": "hello", "new_string": "world"},
            ['{"count":1}'],
            "/note.txt",
        ),
        ("ls", {"path": "/"}, ['{"path":"/note.txt","is_dir":false}'], "/note.txt"),
        ("grep", {"pattern": "hello", "path": "/"}, ["/note.txt\x001:hello\n"], "/note.txt"),
        ("glob", {"pattern": "*.txt", "path": "/"}, ['{"path":"/note.txt","is_dir":false}'], "/note.txt"),
    ],
)
async def test_real_agent_async_file_tool(doc_api, agent_model_factory, tool, args, outputs, expected):
    from deepagents import create_deep_agent
    from langchain_core.messages import AIMessage, ToolMessage

    from contree_sdk import ContreeAsyncSession
    from contree_sdk.langchain import ContreeAsyncSandbox

    for output in outputs:
        doc_api.complete(stdout=output)
    session = ContreeAsyncSession(doc_api.async_client, image="base")
    sandbox = ContreeAsyncSandbox(session)
    model = agent_model_factory(
        responses=[
            AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": "tool-1"}]),
            AIMessage(content="done"),
        ]
    )
    agent = create_deep_agent(model=model, backend=sandbox)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "Use the file tool."}]})
    messages = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert len(messages) == 1
    assert messages[0].status == "success", messages[0].content
    assert expected in str(messages[0].content)
    assert len(doc_api.async_client.calls_for("spawn_instance")) == len(outputs)
    assert len((await session.history())[0]) == len(outputs) + 1
    assert not doc_api.sync.calls_for("spawn_instance")
