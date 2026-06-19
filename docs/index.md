---
icon: book-open-lines
---

# Overview

[![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg?style=flat-square)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk?style=flat-square)](https://pypi.org/project/contree-sdk/)

ConTree is a container runtime, providing **reproducible, versioned filesystem state** — like Git for container execution. The SDK makes this accessible from Python.

## Quick Start

### Installation

Install the SDK from PyPi:

```bash
pip install contree-sdk
```

### Basic Usage

````{tab} Async
```{literalinclude} ../examples/run/run_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## What's Next?

Ready to explore more? Check out our guides:

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} Getting Started
:link: python_sdk/getting-started
:link-type: doc

Detailed setup and basic operations.
:::

:::{grid-item-card} Working with Images
:link: python_sdk/images
:link-type: doc

Pull and import container images.
:::

:::{grid-item-card} Running Commands
:link: python_sdk/running-commands
:link-type: doc

Comprehensive guide to command execution.
:::

:::{grid-item-card} Branching Workflows
:link: python_sdk/branching
:link-type: doc

Create reproducible execution branches.
:::

::::

```{toctree}
:maxdepth: 1
:hidden:

python_sdk/getting-started
python_sdk/images
python_sdk/running-commands
python_sdk/branching

python_sdk/reference/index

integrations/index
```
