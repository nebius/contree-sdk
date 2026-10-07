---
icon: robot
---

# Give a deepagents agent a sandbox

The SDK provides deepagents `BaseSandbox` implementations for command execution
and file transfer. Use `ContreeSandbox` with a sync executor, or
`ContreeAsyncSandbox` with an async executor. A session implements the matching contract.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`../python_sdk/getting-started`.
:::

## Install and test the backend

This integration requires Python 3.11 or newer. Install the development API from
the repository root, as in {doc}`../python_sdk/getting-started`:

```bash
pip install -e ".[langchain,async]"
```

The extra pins deepagents 0.7.10, the version tested with this SDK. Its async file
tools delegate to `aexecute` and `aupload_files`. Version 0.6.8 instead calls sync
methods from those tools and is incompatible with `ContreeAsyncSandbox`.
The sandbox image needs a POSIX shell, Python 3, and the file utilities used by
deepagents, including `grep` for search.

Use the environment variables from {doc}`../python_sdk/getting-started`.
This example exercises the backend directly, so no model credentials are needed.

::::{tab} Sync

<!--
name: test_sandbox; fixtures: deepagents_available, doc_api, capsys
```python
doc_api.complete(stdout="hello\n")
```
-->

```python
import os
from contree_sdk.langchain import ContreeSandbox

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    sandbox = ContreeSandbox(session)
    result = sandbox.execute("echo hello")
    print(result.output, end="")
    print("exit:", result.exit_code)
```

<!--
name: test_sandbox
```python
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert capsys.readouterr().out == "hello\nexit: 0\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_sandbox_async; fixtures: deepagents_available, doc_api, capsys
```python
doc_api.complete(stdout="hello\n")
```
-->

```python
import os
from contree_sdk.langchain import ContreeAsyncSandbox

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    sandbox = ContreeAsyncSandbox(session)
    result = await sandbox.aexecute("echo hello")
    print(result.output, end="")
    print("exit:", result.exit_code)
```

<!--
name: test_sandbox_async
```python
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert capsys.readouterr().out == "hello\nexit: 0\n"
```
-->

::::

The adapter runs commands with `disposable=False`. Its next tool call sees the
filesystem changes. It does not close the session, client, or store. Use SQLite
when the agent needs to resume after a Python restart.

## Connect the backend to an agent

Pass the sandbox as `backend=` to `deepagents.create_deep_agent`. Supply the model
configured by your application. Keep the client open for the entire agent invocation.
The following function accepts that model and uses the environment variables from the getting-started guide:

<!--
name: async test_agent_wiring; fixtures: deepagents_available, doc_api, agent_model_factory
```python
from langchain_core.messages import AIMessage, ToolMessage

doc_api.complete()  # write preflight
doc_api.complete()  # upload and commit
doc_api.complete(stdout="2\n")  # execute
model = agent_model_factory(responses=[
    AIMessage(content="", tool_calls=[{
        "name": "write_file", "args": {"file_path": "/calculator.py", "content": "print(1 + 1)\n"}, "id": "write-1"
    }]),
    AIMessage(content="", tool_calls=[{
        "name": "execute", "args": {"command": "python3 /calculator.py"}, "id": "execute-1"
    }]),
    AIMessage(content="The result is 2."),
])
```
-->

```python
import os
from contree_client.asyncio import ContreeAsyncClient
from deepagents import create_deep_agent
from contree_sdk import ContreeAsyncSession
from contree_sdk.langchain import ContreeAsyncSandbox


async def ask_agent(model):
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
        agent = create_deep_agent(model=model, backend=ContreeAsyncSandbox(session))
        request = {"messages": [{"role": "user", "content": "Create a calculator script and run it."}]}
        return await agent.ainvoke(request)
```

<!--
name: test_agent_wiring
```python
result = await ask_agent(model)
tool_results = [message for message in result["messages"] if isinstance(message, ToolMessage)]
assert len(tool_results) == 2
assert all(message.status == "success" for message in tool_results)
assert "2" in str(tool_results[-1].content)
assert len(doc_api.async_client.calls_for("spawn_instance")) == 3
```
-->

Model-provider installation, credentials, and model selection belong to the agent
application. The SDK does not choose a provider or supply a model key.

## Transfer files and choose sync or async calls

| Sync sandbox                    | Async sandbox                          |
| ------------------------------- | -------------------------------------- |
| `execute(command)`              | `await aexecute(command)`              |
| `upload_files([(path, bytes)])` | `await aupload_files([(path, bytes)])` |
| `download_files([path])`        | `await adownload_files([path])`        |

File paths must be absolute. Transfers return per-file responses; inspect `error`
before reading their content. The async adapter's synchronous methods raise
`NotImplementedError`. Each adapter serializes its own calls, but callers sharing
an executor must coordinate other mutations themselves.

To use another backend implementation, follow {doc}`../python_sdk/customization`.
See {doc}`../python_sdk/reference/langchain` for API signatures.
