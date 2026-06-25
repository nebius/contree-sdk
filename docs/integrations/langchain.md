---
icon: robot
---

# LangChain Integration

[LangChain](https://python.langchain.com/) is a popular framework for building AI agents.
The ConTree integration provides a `ContreeSandbox` backend that lets LangChain agents execute code in isolated, reproducible containers.

Integration is available via `contree-sdk[langchain]`, which provides `ContreeSandbox` — an implementation of [`BaseSandbox`](https://docs.langchain.com/oss/python/deepagents/backends/sandbox) from the [deepagents](https://pypi.org/project/deepagents/) package.

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

2. Set up Nebius IAM token and base URL:

   ```bash
   export NEBIUS_API_KEY="your-nebius-iam-token"
   export NEBIUS_PROJECT_ID="your-project-id"
   ```

3. Set up your LLM provider credentials (e.g. for Anthropic):

   ```bash
   export ANTHROPIC_API_KEY="your-anthropic-api-key"
   ```
