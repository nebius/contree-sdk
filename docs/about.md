# About ConTree

**ConTree** is a code execution runtime, purpose-built to support research on SWE agents, providing **reproducible, versioned filesystem state**

## Key Features

- 🧬 **Automatic container state versioning & branching** - Each command execution creates a new version of the container state
- 🔒 **Secure remote execution** - Run untrusted code safely without managing infrastructure
- 🚀 **Thousands of pre-built SWE images** - Ready-to-use images for SWE-bench and SWE-rebench

## Use Cases

While ConTree is purpose-built to support research on SWE agents, it's just as usable as a general code execution sandbox.

**Primary use case:**

- SWE-bench and SWE-rebench evaluations
- Software engineering agent research and development

**Also, suitable for:**

- General LLM agents requiring code execution
- AI-powered development tools
- Any scenario requiring isolated, reproducible code execution

## Python SDK

Get started with the ConTree Python SDK:

**[Python SDK Documentation →](python_sdk/index.md)**

The Python SDK provides both async and sync APIs for working with ConTree containers, including image management, command execution, and state versioning.
