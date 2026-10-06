---
icon: book-open-lines
---

# ConTree SDK

Run commands in remote sandboxes, keep their filesystem changes, and try different
paths from the same saved state. Use Python for execution and session history;
ConTree stores the filesystem images on the server.

Start with {doc}`python_sdk/getting-started`. It covers credentials, a base image,
and a complete program that prints `Hello from ConTree!`.

## Choose your next task

| I want to…                                            | Read                               |
| ----------------------------------------------------- | ---------------------------------- |
| Run a command and handle its result                   | {doc}`python_sdk/running-commands` |
| Upload inputs and download an output                  | {doc}`python_sdk/files`            |
| Continue work after restarting Python                 | {doc}`python_sdk/sessions`         |
| Try a change and return to a checkpoint               | {doc}`python_sdk/branching`        |
| Stream output or run several processes in one sandbox | {doc}`python_sdk/operation`        |
| Keep a sandbox running between commands               | {doc}`python_sdk/lazy-session`     |
| Import a base image or tag a result                   | {doc}`python_sdk/images`           |
| Build a filesystem from a Dockerfile                  | {doc}`python_sdk/building-images`  |
| Give an agent access to a sandbox                     | {doc}`integrations/langchain`      |
| Change SDK policy or replace a component              | {doc}`python_sdk/customization`    |
| Upgrade an existing application                       | {doc}`python_sdk/migration`        |

## What persists?

A **client** connects to ConTree. A **session** selects an image and records history.
Each command starts a new **operation** from that image.

By default, a command is disposable: its filesystem changes do not advance the
session. Use `disposable=False` when the next command needs those changes.
A session does not keep a process running between commands. Use an operation
context when several processes must share one running sandbox. Use
{doc}`python_sdk/lazy-session` to retain a VM between commands and save it according
to an idle or command-count policy.

Memory stores keep history in Python. SQLite stores keep history across restarts.
Neither store contains the filesystem itself; referenced images must remain on
ConTree. See {doc}`python_sdk/sessions` for ownership and lifetime rules.

```{toctree}
:caption: Start here
:maxdepth: 1
:hidden:

python_sdk/getting-started
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
python_sdk/lazy-session
python_sdk/runtime
python_sdk/images
python_sdk/building-images
python_sdk/caching
```

```{toctree}
:caption: Integrate and extend
:maxdepth: 1
:hidden:

integrations/index
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
