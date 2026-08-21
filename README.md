# 📦 ConTree SDK

[![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg?style=flat-square)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk?style=flat-square)](https://pypi.org/project/contree-sdk/)

**SDK for ConTree: Sandboxes That Branch Like Git**.
ConTree is a container runtime purpose-built to support research on SWE agents, providing **reproducible, versioned filesystem state** — like Git for container execution, accessible from Python.

The low-level HTTP/API client lives in the separate [`contree-client`](https://pypi.org/project/contree-client/) package. `contree-sdk` builds `ContreeSession` — a durable, resumable session with a pluggable history `Store` — on top of it.

👉 **[See full feature list and use cases in the documentation →](https://docs.contree.dev/sdk/)**

## 📥 Get Started

### Installation

Install the SDK from PyPI:

```bash
pip install contree-sdk
```

### Quick Start

<details open>
<summary>🔁 Sync Example</summary>

```python fixture:api_fake_quick_start_sync fixture:name:test_quick_start_sync
from contree_client.sync import ContreeClient
from contree_sdk.session import ContreeSession


def main():
    with ContreeClient(token="fake-token") as client:
        session = ContreeSession(client, image="tag:python:3.11-slim")
        result = session.run(shell='echo "Hello from Contree!"')
        print(result.stdout.as_text())


main()
```

</details>

<details>
<summary>🔀 Async Example</summary>

```python fixture:api_fake_quick_start_async fixture:name:test_quick_start_async
import asyncio

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk.session import ContreeAsyncSession


async def amain():
    async with ContreeAsyncClient(token="fake-token") as client:
        session = ContreeAsyncSession(client, image="tag:python:3.11-slim")
        result = await session.run(shell='echo "Hello from Contree!"')
        print(result.stdout.as_text())


asyncio.run(amain())
```

</details>

## Examples

Ready to explore more? Check out our comprehensive examples in the [`examples/`](https://github.com/nebius/contree-sdk/tree/main/examples) directory.

---

## Development Setup

### Prerequisites

- Python 3.10 - 3.14
- [uv](https://docs.astral.sh/uv/) package manager

### Env setup

```bash
git clone git@github.com:nebius/contree-sdk.git
cd contree-sdk
uv sync --extra dev
```

### Running Checks

Linting and formatting with [Ruff](https://docs.astral.sh/ruff/):

```bash
uv run ruff check .
uv run ruff format .
```

Type checking with [ty](https://docs.astral.sh/ty/):

```bash
make type-check
```

### Running Tests

```bash
uv run pytest
```

### Documentation Dev Server

```bash
make rtd-dev
```

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [Development Setup](#development-setup)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#env-setup)
  - [Running Checks](#running-checks)
  - [Running Tests](#running-tests)
  - [Documentation Dev Server](#documentation-dev-server)
- [Core Concepts](#-core-concepts)
  - [Sessions and Store](#sessions-and-store)
  - [Branching and rollback](#branching-and-rollback)
  - [Resuming a session](#resuming-a-session)
  - [File uploading](#file-uploading)
- [Framework integrations](#framework-integrations)
- [License](#license)

---

## 🧠 Core Concepts

### Sessions and Store

A **`ContreeSession`** is a durable pointer into an image's history. `.run()` returns `contree-client`'s `InstanceResult` as-is — no SDK-invented result type — so `result.stdout`/`.stderr` (decode with `.as_text()`/`.as_bytes()`) and `result.state.exit_code` are exactly what the API returned (`FailedOperationError` is raised instead if the operation itself failed with no result at all). Every non-disposable `.run()` call also appends a new entry to a **`Store`** (the image UUID it produced, the command, the exit code) and moves the session's pointer forward — like a commit advancing a Git branch.

Two `Store` implementations ship with the SDK:

- **`MemoryStore`** (the default when `store=` is omitted) — history lives only for the lifetime of the Python process.
- **`SQLiteStore(path)`** — history is written to a SQLite file (WAL mode), so a session survives process restarts and can be shared across processes.

```python fixture:api_fake_store fixture:name:test_sessions_and_store
from contree_client.sync import ContreeClient
from contree_sdk.session import ContreeSession
from contree_sdk.store import SQLiteStore


def main():
    with ContreeClient(token="fake-token") as client:
        # in-memory history (default)
        memory_session = ContreeSession(client, image="tag:python:3.11-slim")

        # durable history, shared across processes via one SQLite file
        sqlite_session = ContreeSession(
            client, image="tag:python:3.11-slim", store=SQLiteStore("/tmp/contree-example.db")
        )

        result = sqlite_session.run(shell="echo first > /tmp/marker.txt", disposable=False)
        print(result.state.exit_code)

        entries, branches = sqlite_session.history()
        print([entry.kind for entry in entries])


main()
```

### Branching and rollback

A session's history is a DAG, not just a line: you can branch off any point and roll back to an earlier state without losing the commits you moved away from.

```python fixture:api_fake_branching fixture:name:test_branching
from contree_client.sync import ContreeClient
from contree_sdk.session import ContreeSession


def main():
    with ContreeClient(token="fake-token") as client:
        session = ContreeSession(client, image="tag:python:3.11-slim", session_id="demo")
        session.run(shell="echo base > /tmp/state.txt", disposable=False)

        session.create_branch("experiment")
        session.switch_branch("experiment")
        session.run(shell="echo experiment >> /tmp/state.txt", disposable=False)

        # back to the tip of main, the experiment branch is untouched
        session.switch_branch("main")
        print(session.list_branches())


main()
```

### Resuming a session

Pass the same `session_id` and `Store` again to pick up exactly where a session left off — even from a different process, as long as the `Store` is a `SQLiteStore` pointed at the same file.

```python fixture:api_fake_resume fixture:name:test_resume_session
from contree_client.sync import ContreeClient
from contree_sdk.session import ContreeSession
from contree_sdk.store import MemoryStore


def main():
    with ContreeClient(token="fake-token") as client:
        store = MemoryStore()

        first = ContreeSession(client, image="tag:python:3.11-slim", store=store, session_id="my-session")
        first.run(shell="echo hi > /tmp/state.txt", disposable=False)

        # later, elsewhere: resume without repeating `image=`
        resumed = ContreeSession(client, store=store, session_id="my-session")
        assert resumed.image_uuid == first.image_uuid


main()
```

### File uploading

Pass files to bake into the resulting image directly through `.run(files=...)` — the SDK deduplicates uploads by content hash under the hood.

```python fixture:api_fake_file_upload fixture:name:test_file_upload
from contree_client.sync import ContreeClient
from contree_sdk.session import ContreeSession


def main():
    with ContreeClient(token="fake-token") as client:
        session = ContreeSession(client, image="tag:python:3.11-slim")
        result = session.run(
            shell="cat /app.sh",
            files={"/app.sh": b"#!/bin/sh\necho hello\n"},
        )
        print(result.stdout.as_text())


main()
```

---

## Framework integrations

Sandbox adapters for running agent tool calls inside a ConTree session are planned for `contree_sdk.langchain` (`ContreeLCSandbox`) and `contree_sdk.pydantic_ai` (`ContreePAISandbox`), on top of the `ContreeSession`/`Store` design above. Not yet available in this release — `contree_sdk.langchain` still exposes the pre-redesign `ContreeSandbox` and has not been migrated yet; `contree_sdk.pydantic_ai` does not exist yet.

---

## License

Copyright 2026 Nebius B.V.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
<http://www.apache.org/licenses/LICENSE-2.0>

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

_Apache and the Apache logo are either registered trademarks or trademarks of The Apache Software Foundation in the United States and/or other countries._
