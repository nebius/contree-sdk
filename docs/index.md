---
icon: book-open-lines
---

# ConTree SDK

Run commands in remote sandboxes, keep their filesystem changes, and try different
paths from the same saved state. Use Python for execution and session history;
ConTree stores the filesystem images on the server.

Start with {doc}`python_sdk/getting-started`. It covers credentials, a base image,
and a complete program that prints `Hello from ConTree!`. Then continue in order:

1. {doc}`python_sdk/getting-started`
2. {doc}`python_sdk/images`
3. {doc}`python_sdk/building-images`
4. {doc}`python_sdk/advanced`

## Choose your next task

| I want to…                                            | Read                               |
| ----------------------------------------------------- | ---------------------------------- |
| Run a command and handle its result                   | {doc}`python_sdk/running-commands` |
| Select components and control their behavior | {doc}`python_sdk/advanced` |
| Upload inputs and download an output                  | {doc}`python_sdk/files`            |
| Continue work after restarting Python                 | {doc}`python_sdk/sessions`         |
| Try a change and return to a checkpoint               | {doc}`python_sdk/branching`        |
| Stream output or run several processes in one sandbox | {doc}`python_sdk/operation`        |
| Keep a sandbox running between commands               | {doc}`python_sdk/lazy-session`     |
| Import a Docker image                   | {doc}`python_sdk/images`           |
| Build a filesystem from a Dockerfile                  | {doc}`python_sdk/building-images`  |
| Give an agent access to a sandbox                     | {doc}`integrations/langchain`      |
| Change SDK policy or replace a component              | {doc}`python_sdk/customization`    |
| Upgrade an existing application                       | {doc}`python_sdk/migration`        |

## What persists?

The default sandbox reuses one VM between commands. Normal context exit and
explicit `snapshot()` save filesystem changes. An exception discards changes
since the last completed snapshot. The default policy also snapshots after 10
idle seconds. Processes and memory do not survive a snapshot.

History is in memory by default. Supply a SQLite store and a session ID to resume
after Python exits. The store keeps references; filesystem images remain on the
ConTree server. See {doc}`python_sdk/sessions`.

## Advanced control

Use {doc}`python_sdk/advanced` to select components, manage ownership,
and follow build events. {doc}`python_sdk/manual-sandbox` shows explicit assembly.
{doc}`python_sdk/architecture` explains the execution layers. Select an explicit
`ContreeSession` when each command needs an independent operation, or use
{doc}`python_sdk/operation` to manage a VM and its event stream directly.

```{toctree}
:caption: Start here
:maxdepth: 1
:hidden:

python_sdk/getting-started
python_sdk/images
python_sdk/building-images
python_sdk/advanced
```

```{toctree}
:caption: Work with a sandbox
:maxdepth: 1
:hidden:

python_sdk/running-commands
python_sdk/files
```

```{toctree}
:caption: Keep and reuse work
:maxdepth: 1
:hidden:

python_sdk/sessions
python_sdk/branching
python_sdk/operation
python_sdk/detached-operations
python_sdk/lazy-session
python_sdk/caching
```

```{toctree}
:caption: Integrations and advanced usage
:maxdepth: 1
:hidden:

integrations/index
python_sdk/architecture
python_sdk/customization
python_sdk/migration
python_sdk/troubleshooting
```

```{toctree}
:caption: Reference and development
:maxdepth: 1
:hidden:

python_sdk/reference/index
contributing
```
