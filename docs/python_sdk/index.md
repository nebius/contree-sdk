# Contree SDK

<!-- [![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg?style=flat-square)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk?style=flat-square)](https://pypi.org/project/contree-sdk/) -->

Contree is purpose-built to support research on SWE agents, providing **reproducible, versioned filesystem state** — like Git for container execution, accessible from Python.

```{toctree}
:maxdepth: 2
:caption: Contents:
:hidden:

getting-started
images
running-commands
branching

reference/index
```

## Quick Start

### Installation

> ⚠️ **Preview release**
> The SDK is not yet published on PyPI. For now, Contree SDK is distributed as a prebuilt wheel.

Install the SDK from a wheel package:

```bash
pip install contree_sdk-0.0.0.dev2-py3-none-any.whl
```

### Basic Usage

````{tab} Async
```{literalinclude} ../../examples/run/run_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## What's Next?

Ready to explore more? Check out our guides:

- **[Getting Started](getting-started.md)** - Detailed setup and basic operations
- **[Working with Images](images.md)** - Pull and import container images
- **[Running Commands](running-commands.md)** - Comprehensive guide to command execution
- **[Branching Workflows](branching.md)** - Create reproducible execution branches
