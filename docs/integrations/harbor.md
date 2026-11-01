# Harbor on ConTree

The Harbor environment starts one ConTree `AsyncOperation` per trial. Harbor commands run as subprocesses in that operation. Files and background processes remain available between commands. `stop()` ends the main process and saves the final image.

Install Harbor 0.22 alongside `contree-sdk` and select the backend:

```bash
harbor run -t hello-world/hello-world -a oracle \
  --env contree_sdk.harbor:ConTreeEnvironment --ek profile=stage
```

Tasks need a prebuilt OCI registry image in `[environment].docker_image`. The image must contain Bash and `sleep`. Dockerfile builds, Compose, GPUs, custom mounts, task MCP servers, and restricted networking are unsupported. Harbor's standard log mounts use file transfers. The adapter supports the image's default user, a numeric UID, or `root`.

The SDK's `AsyncClientFileTransfer` uploads files to ConTree storage. The client applies them to the live operation. Live file downloads use the running-instance inspection API. Directory uploads merge with existing contents. All Harbor calls on one environment are serialized.

`operation_timeout` defaults to 1,000 seconds per command; Harbor's command timeout overrides it. `readiness_timeout` defaults to 120 seconds for the main process to start. Harbor applies `environment.build_timeout_sec` to the full environment setup. `vm_timeout` defaults to 3,600 seconds for the whole operation. `snapshot_timeout` defaults to 120 seconds for final shutdown, and `terminate_timeout` defaults to 5 seconds when stopping a timed-out command. File transfers have a 600-second limit. The backend may impose a lower operation lifetime limit.

An injected `client=ContreeAsyncClient(...)` remains caller-owned. Otherwise, the adapter opens and closes the client from the selected ConTree profile. Harbor's `delete` option has no effect: ConTree manages image retention separately.
