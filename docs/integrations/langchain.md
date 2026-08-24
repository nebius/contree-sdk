---
icon: robot
---

# LangChain Integration

[LangChain](https://python.langchain.com/) is a popular framework for building AI agents.
The ConTree integration provides a `ContreeSandbox` backend that lets LangChain agents execute code in isolated, reproducible containers, backed by a `ContreeSession`.

Integration is available via `contree-sdk[langchain]`, which provides `ContreeSandbox` — an implementation of [`BaseSandbox`](https://docs.langchain.com/oss/python/deepagents/backends/sandbox) from the [deepagents](https://pypi.org/project/deepagents/) package.

`ContreeSandbox` wraps a (sync) `ContreeSession`; deepagents' async sandbox methods (`aexecute()`, etc.) already bridge to it via a thread pool, so async agent code (`await agent.ainvoke(...)`) works without contree-sdk needing its own async sandbox variant.

## Using ContreeSandbox

```{literalinclude} ../../examples/langchain/langchain_basic.py
:language: python
:linenos:
```

## Setup

1. Install the dependencies:

   ```bash
   pip install "contree-sdk[langchain]"
   ```

2. Set up ConTree credentials. The example above uses `ContreeClient.from_profile()`, which
   reads a saved CLI profile (or `CONTREE_PROFILE`); see {doc}`../python_sdk/getting-started`
   for that and the other construction options, including `CONTREE_TOKEN`/`CONTREE_URL`.

3. Set up your LLM provider credentials (e.g. for Nebius AI Studio, used by the example above):

   ```bash
   export NEBIUS_API_KEY="your-nebius-ai-studio-api-key"
   ```

   Note: `contree_client.profiles.from_env()` also accepts `NEBIUS_API_KEY` as a fallback for the
   ConTree token itself. If you use both a ConTree instance and Nebius AI Studio, use `CONTREE_TOKEN`
   explicitly for ConTree to avoid the two keys colliding.
