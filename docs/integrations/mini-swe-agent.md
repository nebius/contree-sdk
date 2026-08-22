---
icon: robot
---

# Mini-SWE-Agent Integration

[Mini-SWE-Agent](https://mini-swe-agent.com/latest/) is a lightweight software engineering agent.
The ConTree integration enables it to execute code in isolated, reproducible containers.

:::{warning}
As of mini-swe-agent 2.4.6 (the latest release at the time of writing), its bundled
`ContreeEnvironment` (`minisweagent.environments.extra.contree`) still targets the pre-redesign
contree-sdk API — it imports `ContreeSync`, `contree_sdk.config.ContreeConfig`, and
`contree_sdk.sdk.objects.image.ContreeImageSync`, none of which exist in this contree-sdk release.
**This integration does not currently work.** The fix needs to land upstream in
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent), porting `ContreeEnvironment` onto
`contree_sdk.session.ContreeSession` — see {doc}`langchain` for what that shape looks like for
another framework's sandbox interface.
:::

## Setup

Once mini-swe-agent's `ContreeEnvironment` is updated, the integration is expected to be installed via its own extra:

```bash
pip install "mini-swe-agent[contree]"
```

`contree-sdk[examples]` also pulls in `mini-swe-agent` for running the examples in this repository.
