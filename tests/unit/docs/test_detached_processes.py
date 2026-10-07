"""Run the documented producer and consumer without shared Python variables."""

import ast
import inspect
import re
from pathlib import Path

import pytest


@pytest.mark.parametrize("offset", [0, 2], ids=["sync", "async"])
async def test_detached_examples_use_independent_namespaces(doc_api, offset):
    source = Path(__file__).resolve().parents[3] / "docs/python_sdk/detached-operations.md"
    visible = re.sub(r"<!--.*?-->", "", source.read_text(), flags=re.DOTALL)
    blocks = re.findall(r"```python\n(.*?)```", visible, flags=re.DOTALL)
    doc_api.complete(stdout="saved\n")
    for block in blocks[offset : offset + 2]:
        code = compile(block, str(source), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        result = eval(code, {})  # noqa: S307 - execute this repository's documented scenario
        if inspect.isawaitable(result):
            await result
    client = doc_api.sync if offset == 0 else doc_api.async_client
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
