# 📦 Contree SDK

[![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg?style=flat-square)](https://pypi.org/project/contree-sdk/)
![Python](https://img.shields.io/pypi/pyversions/contree-sdk?style=flat-square)

Contree SDK lets you run code in isolated containers **with reproducible, versioned state**
— like Git for container execution, accessible from Python.

**What you get:**
- 🧬 Automatic container state versioning & branching
- 🔁 Seamless async *and* sync APIs
- 🔒 Secure remote execution without managing infrastructure

## 📥 Get Started

### Installation

> ⚠️ **Preview release**  
> The SDK is not yet published on PyPI
> For now, Contree SDK is distributed as a prebuilt wheel.

Install the SDK from a wheel package:

```bash
pip install contree_sdk-0.0.0.dev2-py3-none-any.whl
```

### Quick Start

<details open>
<summary>🔀 Async Example</summary>

```python
import asyncio
from contree_sdk import Contree

async def main():
    # Get client
    contree = Contree(token='your-token')
    
    # Get image
    image = await contree.images.pull("ubuntu:latest")
    
    # Run command
    result = await image.run(shell='echo "Hello from Contree!"')
    
    # Output result
    print(result.stdout)

asyncio.run(main())
```

</details>

<details>
<summary>🔁 Sync Example</summary>

```python
from contree_sdk import ContreeSync

def main():
    # Get client
    contree = ContreeSync(token='your-token')
    
    # Get image
    image = contree.images.pull("ubuntu:latest")
    
    # Run command
    result = image.run(shell='echo "Hello from Contree!"').wait()
    
    # Output result
    print(result.stdout)

main()
```

</details>


## 🤔 Why Contree?

Use Contree when you need to:
- Run untrusted or isolated code safely
- Reproduce execution environments exactly
- Branch execution flows without rebuilding images
- Build tools that execute code (agents, evaluators, pipelines)

Typical use cases:
- LLM agents & sandboxes
- CI-like workflows without CI
- Reproducible research & experiments


## 📚 Examples

Ready to explore more? Check out our comprehensive examples:

- **[Session Management](./examples/session/)** - Working with persistent sessions and state management
- **[Image Operations](./examples/images/)** - Advanced image pulling, versioning, and management
- **[Branching Workflows](./examples/branching/)** - Complex workflow patterns with image branching

Explore all examples in the [`examples/`](./examples/) directory.
