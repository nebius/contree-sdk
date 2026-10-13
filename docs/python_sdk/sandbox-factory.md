# Create a sandbox session

`create_sandbox_session` selects a synchronous or asynchronous context when you
use `with` or `async with`. The default session shares one VM between commands.
`create_sync_sandbox_session` and `create_async_sandbox_session` provide the same
configuration with only the corresponding context protocol.

Install this checkout as described in {doc}`getting-started`. Async code needs
`pip install -e ".[async]"`. Use an image already available on your endpoint;
the examples require a POSIX shell, `sleep`, `echo`, and `cat`.

## Run two commands

Configure the connection as described in {ref}`sandbox-connection`. Replace
`tag:alpine:latest` with an image available on your endpoint.
Save either program as a Python file and run it normally.

<!-- name: test_factory_sync; fixtures: sandbox_api -->

```python
from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        session.run(shell="echo 'Hello from ConTree!' > /message.txt")
        result = session.run("cat", args=["/message.txt"])
        print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_factory_sync
```python
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 1
assert len(sandbox_api.sync.calls_for("operation_subprocess_create")) == 2
assert len(sandbox_api.sync.calls_for("operation_subprocess_kill")) == 1
```
-->

<!-- name: test_factory_async; fixtures: sandbox_api -->

```python
import asyncio

from contree_sdk import create_async_sandbox_session


async def main() -> None:
    async with create_async_sandbox_session(image="tag:alpine:latest") as session:
        await session.run(shell="echo 'Hello from ConTree!' > /message.txt")
        result = await session.run("cat", args=["/message.txt"])
        print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_factory_async
```python
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 1
assert len(sandbox_api.async_client.calls_for("operation_subprocess_create")) == 2
assert len(sandbox_api.async_client.calls_for("operation_subprocess_kill")) == 1
```
-->

Both programs print `Hello from ConTree!`. Constructing the context performs no
I/O. Entry resolves the image and prepares the session; the first command starts
the VM. Normal exit saves pending changes and stops the VM. An exception or
cancellation discards changes since the last completed snapshot.

The default `IdleSnapshotPolicy(60)` saves and stops the VM after 60 idle seconds.
The next command starts from the saved image. Files survive this boundary;
processes, memory, and sockets do not. Default history is in memory, so retain a
store and session ID when you need to resume after leaving the context. See
{doc}`lazy-session` for snapshot policies and limitations of live file access.

(sandbox-connection)=

## Select a connection source

Configure the endpoint URL, token, and AI project for your deployment. The
project identifies where the sandbox runs; omitting it is not a complete working
configuration. Use a matching IAM or JWT token.

| Setting             | Environment                              | Profile / INI        | Direct factory argument      |
| ------------------- | ---------------------------------------- | -------------------- | ---------------------------- |
| Endpoint            | `CONTREE_URL`                            | `url`                | `url`                        |
| Token               | `CONTREE_TOKEN` or `NEBIUS_API_KEY`      | `token`              | `token`                      |
| AI project          | `CONTREE_PROJECT` or `NEBIUS_AI_PROJECT` | `project`            | `project`                    |
| Authentication type | Set through an explicit or saved Profile | `auth_type` / `type` | `auth_type="iam"` or `"jwt"` |

The SDK delegates environment parsing to contree-client. Its environment helper
does not read an authentication-type variable; use a Profile or direct arguments
when you need to select that field explicitly.

Use exactly one explicit source:

| Source             | Arguments                                | Behavior                                                                                                     |
| ------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Direct credentials | `url`, `project`, `token`, `auth_type`   | Build a regular client `Profile`. Token is required. JWT requires URL; IAM can use the client's default URL. |
| Profile object     | `profile=profile`                        | Use that exact profile. Do not combine it with direct credentials or `config_path`.                          |
| Named profile      | `profile="work"`, optional `config_path` | Resolve that name through contree-client.                                                                    |
| Explicit INI       | `config_path="config.ini"`               | Resolve the file's active profile, or the name selected by `CONTREE_PROFILE`.                                |
| Automatic          | Omit all source arguments                | Use `contree_client.profiles.from_env()`, then the client's default profile resolution.                      |

Direct credentials cannot be combined with `profile` or `config_path`.
Incomplete explicit credentials raise an error rather than falling back to ENV.
An explicit source takes priority over ENV. Without one, the environment needs
both `CONTREE_URL` and `CONTREE_TOKEN` (or `NEBIUS_API_KEY`). Provide the project
through `CONTREE_PROJECT` (or `NEBIUS_AI_PROJECT`).

For INI resolution, contree-client uses an explicit profile name, then
`CONTREE_PROFILE`, then the active profile in the file. Its default files are
`cli.ini` and `auth.ini` under `CONTREE_HOME`; `auth.ini` takes priority. Without
`CONTREE_HOME`, the client uses its XDG configuration directory. A supplied
`config_path` replaces the auth file path and can be named `config.ini`; the
client also reads `cli.ini` from the same directory.

For example, a JWT configuration file contains:

```ini
[DEFAULT]
profile = work

[profile:work]
type = jwt
url = https://your-contree-endpoint
token = your-token
project = your-ai-project
```

Use `type = iam` for an IAM profile. This selects the client's existing profile
behavior; the SDK does not acquire or refresh IAM credentials itself.

<!-- name: test_factory_direct_profile; fixtures: sandbox_api -->

```python
from contree_sdk import create_sync_sandbox_session, profile_from_args


profile = profile_from_args(
    url="https://contree.example.com",
    token="your-token",
    project="your-ai-project",
    auth_type="iam",
)
with create_sync_sandbox_session(image="tag:alpine:latest", profile=profile) as session:
    session.run("echo", args=["Hello!"])
```

`profile_from_args` only constructs a `Profile`; it does not write an INI file.
You can instead pass the same four arguments directly to any factory.

## Advanced: select the session class and components

`session_type` accepts a class. Without it, the context selects `LazySession` or
`AsyncLazySession`. An explicitly selected class must match the context mode:
`session_type=AsyncLazySession` with a synchronous `with` raises `TypeError`
before creating a client. The same rule applies to `client_type` and supplied
storage, cache, file transfer, and client objects.

<!-- name: test_factory_components; fixtures: sandbox_api -->

```python
from contree_sdk import LazySession, create_sync_sandbox_session
from contree_sdk.cache import SyncMemoryCache
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.store import SyncSQLiteStore


with SyncSQLiteStore("sandbox.db") as storage, SyncMemoryCache() as cache:
    with create_sync_sandbox_session(
        image="tag:alpine:latest",
        session_type=LazySession,
        session_id="work",
        storage=storage,
        cache=cache,
        cache_ttl=60,
        cwd="/",
        env={"LANG": "C.UTF-8"},
        session_kwargs={"snapshot_policy": IdleSnapshotPolicy(120), "snapshot_timeout": 30},
    ) as session:
        session.run("echo", args=["Saved on exit"])
```

Custom classes implement `SyncExecutor` or `AsyncExecutor`. Lazy subclasses
receive an underlying `ContreeSession` or `ContreeAsyncSession`, plus
`session_kwargs`. Other classes receive the client and the standard Session
constructor arguments, plus `session_kwargs`. Subclass an existing session to
retain its execution and lifecycle rules. The factory never substitutes a
different class for an explicitly selected class.

Selecting `ContreeSession` or `ContreeAsyncSession` retains that class's normal
behavior: each command uses a separate operation and defaults to disposable.
Pass `disposable=False` to keep results. See {doc}`sessions`.

| Argument                      | Purpose                                                                                                                                                                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `image`, `session_id`         | Initial image or stored session to resume. At least one is required.                                                                                                                                                      |
| `storage`                     | Session history store; defaults to a new memory store of the selected mode.                                                                                                                                               |
| `cache`, `cache_ttl`          | Optional upload reuse through `CachedFileTransfer`; local entries expire after 60 seconds by default. Choose a TTL no longer than your server's upload retention.                                                         |
| `cwd`, `env`, `commit_policy` | Configuration of the underlying session.                                                                                                                                                                                  |
| `file_transfer`               | Replace file I/O; when `cache` is supplied, the cache wraps this transfer.                                                                                                                                                |
| `session_kwargs`              | Additional constructor arguments for the selected session class, including lazy snapshot options. Factory-managed arguments take priority over duplicates in this mapping.                                                                      |
| `client`                      | Borrow an already configured client. Cannot be combined with connection settings or `client_type`.                                                                                                                        |
| `client_type`                 | Select a contree-client class. Defaults are HTTPX for sync and aiohttp for async.                                                                                                                                         |
| Other keyword arguments       | Forwarded unchanged to the client constructor through `from_profile`, including `timeout`, `retry`, `identity`, TLS and backend-specific settings. Credentials use the source arguments above; use `url`, not `base_url`. |

Uploaded-file cache entries are separated by endpoint, project, and token. The
cache does not replace history storage or enable uploads to an already running
LazySession VM.

## Advanced: ownership and extension

Each context object permits one entry, including a failed entry. Re-entry,
nesting, and mixing sync/async entry on that object raise `RuntimeError`; call the
factory again to get a new context.

The factory closes resources it creates. Supplied clients, storage, caches, and
file transfers remain caller-owned and must be ready for use. A session's context
exit runs before the owned client closes. Async cleanup is joined even when the
caller cancels again; a body exception takes priority over cleanup errors.

All three factories call `session_maker(context_type, ...)` with their respective
context class. `SandboxSessionContext` composes `SyncSandboxSessionContext` and
`AsyncSandboxSessionContext`. For a custom context, supply a class accepting
`SandboxConfig` to `session_maker`. See {doc}`reference/sandbox` for the shared
parameter signature and context contracts.

For complete sync and async examples of the component assembly behind this
factory, see {doc}`manual-sandbox`.
