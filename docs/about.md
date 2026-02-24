# About ConTree

**ConTree** is a code execution runtime, providing **reproducible, versioned filesystem state**

## Key Features

- 🧬 **Automatic container state versioning & branching** - Each command execution creates a new version of the container state
- 🔒 **Secure remote execution** - Run untrusted code safely without managing infrastructure
- 🚀 **Thousands of pre-built SWE images** - Ready-to-use images for SWE-bench and SWE-rebench

## Use Cases

ConTree's reproducible container execution environment serves various applications:

**AI Agents:**

- SWE-bench type agent evaluation
- AI agent code execution
- Coding assistant sandboxing

**CI/CD:**

- Per-PR environment snapshots
- Flaky test reruns from same state
- Local CI failure reproduction

**Security:**

- User-submitted code sandboxing
- Untrusted dependency isolation
- Malware sample analysis

## Python SDK

Get started with the ConTree Python SDK:

**[Python SDK Documentation →](python_sdk/index.md)**

The Python SDK provides both async and sync APIs for working with ConTree containers, including image management, command execution, and state versioning.
