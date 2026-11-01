# Run Harbor on ConTree

:::{note}
The integration currently supports the minimum features needed to run Terminal
Bench 2.1 (TB2.1). Broader Harbor support is planned; other datasets have not
been validated.
:::

## Quick start

This integration requires Harbor 0.22.x and Python 3.12 or newer. Install with
`pip install 'contree-sdk[harbor]'` and configure your connection as described below.

```bash
harbor run -t hello-world/hello-world -a oracle \
  --env contree_sdk.harbor:ConTreeEnvironment
```

## Connection configuration

Use your saved default profile, or supply the connection through environment
variables:

```bash
export CONTREE_URL="https://api.tokenfactory.nebius.com/sandboxes"
export CONTREE_TOKEN="your-api-key"
export CONTREE_PROJECT="your-ai-project"
```

| Variable                                 | Purpose                                                                                                        |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `CONTREE_URL`                            | ConTree API endpoint.                                                                                          |
| `CONTREE_TOKEN` or `NEBIUS_API_KEY`      | Authentication token.                                                                                          |
| `CONTREE_PROJECT` or `NEBIUS_AI_PROJECT` | AI project that runs the sandbox.                                                                              |
| `CONTREE_PROFILE`                        | Saved profile name; otherwise, use the active profile from the configuration files.                            |
| `CONTREE_HOME`                           | Directory containing `cli.ini` and `auth.ini`. Defaults to `$XDG_CONFIG_HOME/contree`, or `~/.config/contree`. |

Without an explicit `profile` option, environment credentials take priority when
both URL and token are set; otherwise, the client loads a saved profile.
`--ek profile=work` selects that saved profile directly, taking priority over the
environment variables.

See [SDK connection configuration](../python_sdk/getting-started.md#connection-sources)
for more about credentials, saved profiles, and configuration files.

## Environment options

Pass ConTree-specific options with `--ek NAME=VALUE`, or through
`environment.kwargs` in a Harbor job configuration.

| Option              | Default                                   | Description                                                                                                            |
| ------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `profile`           | Automatic selection                       | Saved ConTree profile name, for example `--ek profile=work`.                                                           |
| `snapshot_idle_sec` | `300`                                     | Positive idle delay in seconds before saving a snapshot, for example `--ek snapshot_idle_sec=600`.                     |
| `client`            | Created from the connection configuration | Python only: supply an async ConTree client. It provides the connection instead of `profile` and remains caller-owned. |

The environment keeps one VM running across commands, so files and background
processes remain available until an idle snapshot. Background processes end at
a snapshot boundary and do not resume with the next command.

## Validated datasets

- Terminal Bench 2.1 (TB2.1)

## Current limitations

- Each task needs `[environment].docker_image` set to a prebuilt OCI registry
  image containing Bash and `sleep`. Dockerfile builds are not supported.
- Commands use the image's default user. Harbor can override it with `root` or
  a numeric UID; other user names are not supported.
- Compose, GPUs, custom host mounts, and restricted networking are not supported.
- Operation resource settings and Docker inside the VM are not exposed by this
  integration. These and other ConTree capabilities will be added and validated
  as datasets require them.
- `--no-delete` currently behaves like `--delete`: stopping cancels the VM and
  does not save a final image.

## Implementation

The adapter uses the SDK's `AsyncLazySession` to run Harbor commands as
subprocesses in one ConTree VM. After an idle snapshot, the next command starts
a VM from the saved image.
