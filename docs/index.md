# Contree

**Contree** is a code execution runtime, purpose-built to support research on SWE agents, providing **reproducible, versioned filesystem state**

```{toctree}
:maxdepth: 2
:caption: Contents:


self
python_sdk/index
integrations/mini-swe-agent
```

## Key Features

- 🧬 **Automatic container state versioning & branching** - Each command execution creates a new version of the container state
- 🔒 **Secure remote execution** - Run untrusted code safely without managing infrastructure
- 🚀 **Thousands of pre-built SWE images** - Ready-to-use images for SWE-bench and SWE-rebench

## Use Cases

While Contree is purpose-built to support research on SWE agents, it's just as usable as a general code execution sandbox.

**Primary use case:**

- SWE-bench and SWE-rebench evaluations
- Software engineering agent research and development

**Also suitable for:**

- General LLM agents requiring code execution
- AI-powered development tools
- Any scenario requiring isolated, reproducible code execution

## Python SDK

Get started with the Contree Python SDK:

**[Python SDK Documentation →](python_sdk/index.md)**

The Python SDK provides both async and sync APIs for working with Contree containers, including image management, command execution, and state versioning.
