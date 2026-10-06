---
icon: plug
---

# Connect an agent framework

Use the deepagents sandbox adapter to expose a session to agent tools. It supports
sync and native async execution and retains filesystem changes between tool calls.
It also accepts a custom executor implementation.

| Integration                          | Status for this SDK API                                       |
| ------------------------------------ | ------------------------------------------------------------- |
| deepagents / LangChain               | Supported through `ContreeSandbox` and `ContreeAsyncSandbox`. |
| mini-swe-agent 2.4.6 bundled adapter | Uses the removed API; see the compatibility note.             |

```{toctree}
:maxdepth: 1

langchain
mini-swe-agent
```
