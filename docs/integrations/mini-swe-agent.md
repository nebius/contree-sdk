---
icon: robot
---

# mini-swe-agent compatibility

The `ContreeEnvironment` bundled with mini-swe-agent 2.4.6 uses the previous SDK
API, including `ContreeSync` and SDK image objects. Those imports are removed in
this release. That adapter cannot run with the new session API.

Installing `mini-swe-agent[contree]` does not by itself port the adapter.
Use {doc}`langchain` for a supported integration, or adapt the environment to
`ContreeSession` and its `run()` result. The public execution contracts are described
in {doc}`../python_sdk/customization`.

This compatibility statement applies to the inspected 2.4.6 adapter. Check the
adapter shipped with another mini-swe-agent version before using it.
