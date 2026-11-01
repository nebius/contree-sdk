# Run Harbor on ConTree

## Quick start

This integration requires Harbor 0.22.x and Python 3.12 or newer. Install with
`pip install 'contree-sdk[harbor]'` and configure your default ConTree profile.

```bash
harbor run -t hello-world/hello-world -a oracle \
  --env contree_sdk.harbor:ConTreeEnvironment
```

To use another ConTree profile, add `--ek profile=<<value>>` with the desired profile name.

## Current limitations

- Each task needs `[environment].docker_image` set to a prebuilt OCI registry
  image containing Bash and `sleep`. Dockerfile builds are not supported.
- Commands use the image's default user. Harbor can override it with `root` or
  a numeric UID; other user names are not supported.
- Compose, GPUs, custom host mounts, and restricted networking are not supported.
- `--no-delete` currently behaves like `--delete`: stopping cancels the VM and
  does not save a final image.

## Runtime options

The environment keeps one VM running across commands, so files and background
processes remain available until an idle snapshot. The default idle delay is
300 seconds; set `--ek snapshot_idle_sec=SECONDS` to change it. Background
processes end at a snapshot boundary and do not resume with the next command.

## Implementation

The adapter uses the SDK's `AsyncLazySession` to run Harbor commands as
subprocesses in one ConTree VM. After an idle snapshot, the next command starts
a VM from the saved image.
