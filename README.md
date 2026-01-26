# 📦 Contree

<!-- [![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg?style=flat-square)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk?style=flat-square)](https://pypi.org/project/contree-sdk/) -->

Contree is a container runtime purpose-built to support research on SWE agents, providing **reproducible, versioned filesystem state** — like Git for container execution, accessible from Python.

👉 **[See full feature list and use cases in the documentation →](docs/index.md)**

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
    contree = Contree(token="your-token")

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
    contree = ContreeSync(token="your-token")

    # Get image
    image = contree.images.pull("ubuntu:latest")

    # Run command
    result = image.run(shell='echo "Hello from Contree!"').wait()

    # Output result
    print(result.stdout)

main()
```

</details>

## 📚 Examples

Ready to explore more? Check out our comprehensive examples:

- **[Session Management](./examples/session/)** - Working with persistent sessions and state management
- **[Image Operations](./examples/images/)** - Advanced image pulling, versioning, and management
- **[Branching Workflows](./examples/branching/)** - Complex workflow patterns with image branching

Explore all examples in the [`examples/`](./examples/) directory

---

## License

Copyright 2026 Nebius B.V.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
<http://www.apache.org/licenses/LICENSE-2.0>

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

_Apache and [Apache Spark](http://spark.apache.org/) are either registered trademarks or trademarks of the Apache Software Foundation in the United States and/or other countries._
