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

Your sandbox can keep more than its latest result. Save a checkpoint, try an
experiment on another branch, and return to the baseline without repeating setup.
Continue with {doc}`Work with a Session <python_sdk/session-model>` to learn how
snapshots, branches, rollback, and persistent history fit together.

## Choose your next task

| I want to…                                            | Read                              |
| ----------------------------------------------------- | --------------------------------- |
| Understand sessions, snapshots, and branches          | {doc}`python_sdk/session-model`   |
| Select components and control their behavior          | {doc}`python_sdk/advanced`        |
| Upload inputs and download an output                  | {doc}`python_sdk/files`           |
| Continue work after restarting Python                 | {doc}`python_sdk/sessions`        |
| Try a change and return to a checkpoint               | {doc}`python_sdk/branching`       |
| Stream output or run several processes in one sandbox | {doc}`python_sdk/operation`       |
| Import a Docker image                                 | {doc}`python_sdk/images`          |
| Build a filesystem from a Dockerfile                  | {doc}`python_sdk/building-images` |
| Give an agent access to a sandbox                     | {doc}`integrations/langchain`     |
| Change SDK policy or replace a component              | {doc}`python_sdk/customization`   |
| Upgrade an existing application                       | {doc}`python_sdk/migration`       |

## What persists?

The default sandbox reuses one VM between commands. Normal context exit and
explicit `snapshot()` save filesystem changes. An exception discards changes
since the last completed snapshot. The default policy also snapshots after 10
idle seconds. Snapshots are lightweight and can run after every command, but they
stop the VM. Processes and memory do not survive. An unchanged filesystem can
produce the same `image_uuid`; this is normal.

Select `session_type=ContreeSession` or `ContreeAsyncSession` to save each command
automatically in a separate VM. `disposable=True` leaves the session image
unchanged. See [Save after every command](python_sdk/session-model.md#save-after-every-command).

History is in memory by default. Supply a SQLite store and a session ID to resume
after Python exits. The store keeps references; filesystem images remain on the
ConTree server. See {doc}`python_sdk/sessions`.

## Advanced control

Use {doc}`python_sdk/advanced` to select components, manage ownership,
and follow build events. {doc}`python_sdk/manual-sandbox` shows explicit assembly.
Use {doc}`python_sdk/operation` to manage subprocesses and their event stream.

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
:caption: Work with a Session
:maxdepth: 1
:hidden:

python_sdk/session-model
python_sdk/branching
python_sdk/sessions
python_sdk/files
python_sdk/operation
python_sdk/detached-operations
python_sdk/caching
```

```{toctree}
:caption: Integrations
:maxdepth: 1
:hidden:

integrations/langchain
integrations/mini-swe-agent
```

```{toctree}
:caption: Advanced Usage
:maxdepth: 1
:hidden:

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
