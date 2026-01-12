# 📦 Contree SDK

## Table of Contents

- [Installation](#-installation)
  - [Installation from Nebius Artifactory](#installation-from-nebius-artifactory)
- [Quick Start](#-quick-start)
- [Core Concepts](#-core-concepts)
  - [Sessions and Versioning](#sessions-and-versioning)
  - [Subprocess-like interface](#subprocess-like-interface)
  - [Stable image UUID](#stable-image-uuid)
  - [Async/sync clients and objects](#asyncsync-clients-and-objects)
- [Advanced Usage](#️-advanced-usage)
  - [Client configuration](#client-configuration)
  - [Objects reusing](#objects-reusing)
  - [File uploading](#file-uploading)

---

## 📥 Installation

### Installation from Nebius Artifactory

> [!NOTE]
> While the project is under development, it's not available publicly. It's available only through Nebius `ai-rnd` PyPI registry.

1. Open https://artifactory.nebius.dev/
2. Log in using SSO
3. In top right corner click on your profile
4. Click on `Set Me Up`
5. Select `pypi`
6. Inside repository selector choose `ai-rnd`
7. Inside `Configure` tab click on `Generate Token & Create Instructions`
8. Copy and save your token somewhere
9. Add the following to your `~/.pip/pip.conf` file inside `[global]` section:

```ini
extra-index-url = https://<EMAIL>:<TOKEN>@artifactory.nebius.dev/artifactory/api/pypi/ai-rnd/simple
```

10. Replace `<EMAIL>` with your Nebius email (e.g. `yourname@nebius.com`) and `<TOKEN>` with your saved token
11. Install the package: `pip install contree-sdk`

> [!TIP]
> For package managers that don't use `~/.pip/pip.conf` (e.g. `uv`, `pdm`) please refer to their respective documentation.

---

## 🚀 Quick Start

<details open>
<summary>🔀 Async Example</summary>

<!-- name: test_quick_start_async
```python
import asyncio
import stat
from unittest.mock import AsyncMock, MagicMock, patch

# Mock the SDK internals to prevent real API calls
mock_image = MagicMock()
mock_image.run = AsyncMock(return_value=MagicMock(
    stdout='output', stderr='',
    run=AsyncMock(return_value=MagicMock(
        ls=AsyncMock(return_value=[MagicMock(name='file1', is_dir=False, is_file=True, download=AsyncMock())])
    ))
))
mock_image.session = AsyncMock(return_value=MagicMock(
    run=AsyncMock(return_value=MagicMock(stdout='result')),
    download=AsyncMock(),
    read=AsyncMock(return_value=b'log content')
))

mock_contree = MagicMock()
mock_contree.images = AsyncMock(return_value=[mock_image])
mock_contree.images.pull = AsyncMock(return_value=mock_image)

patch('contree_sdk.Contree', return_value=mock_contree).start()
```
-->
```python
import asyncio
import stat

from contree_sdk import Contree
from contree_sdk.utils.objects.file import UploadFileSpec

async def amain():
    # create client
    contree = Contree(token='real-contree-token')

    # list images
    images = await contree.images()

    # pulling existing image
    ubuntu_image = await contree.images.pull("ubuntu:latest")

    # pulling image from a remote registry
    busybox_image = await contree.images.pull("docker://docker.io/busybox:latest")

    # running command
    result0 = await ubuntu_image.run(
        command='/app.sh',
        args=('arg1', 'arg2'),
        stdin='input',
        env=dict(http_proxy='http://10.20.30.40:1234'),
        files=[
            UploadFileSpec(source='/local/files/app.sh', mode=stat.S_IXUSR),
            UploadFileSpec(source='/local/files/data_ver1.csv', path='/data.csv'),
        ]
    )
    print(result0.stdout)
    print(result0.stderr)

    # running next command
    result1 = await result0.run(shell='echo output.csv | grep something')

    # getting files and directories by path
    items = await result1.ls('files/path')
    print(len(items))

    # iterating through files and directories by path
    for item in await result1.ls('~'):
        print(item.name, item.is_dir)
        if item.is_file:
            # download file
            await item.download('/local/files/downloaded/')

    # using session
    session = await busybox_image.session()
    await session.run(
        command='/bin/app',
        files=[UploadFileSpec(source='/local/files/app', path='bin/app', mode=stat.S_IXUSR)]
    )
    res = await session.run(command='/bin/cat', args=('result.txt',))
    print(res.stdout)

    # downloading file from session
    await session.download('/tmp/log.jsonl', '/local/logs/session_1.log')

    # or simply reading from file
    content = await session.read('/tmp/log.jsonl')
    print(content.decode())


asyncio.run(amain())
```

</details>

<details>
<summary>🔁 Sync Example</summary>

<!-- name: test_quick_start_sync
```python
import stat
from unittest.mock import MagicMock, patch

# Mock the SDK internals to prevent real API calls
mock_run_result = MagicMock()
mock_run_result.stdout = 'output'
mock_run_result.stderr = ''
mock_run_result.run = MagicMock(return_value=MagicMock(wait=MagicMock(return_value=MagicMock(
    ls=MagicMock(return_value=[MagicMock(name='file1', is_dir=False, is_file=True, download=MagicMock())])
))))

mock_pending = MagicMock()
mock_pending.wait = MagicMock(return_value=mock_run_result)

mock_image_sync = MagicMock()
mock_image_sync.run = MagicMock(return_value=mock_pending)
mock_image_sync.session = MagicMock(return_value=MagicMock(
    run=MagicMock(return_value=MagicMock(wait=MagicMock(return_value=MagicMock(stdout='result')))),
    download=MagicMock(),
    read=MagicMock(return_value=b'log content')
))

mock_contree_sync = MagicMock()
mock_contree_sync.images = MagicMock(return_value=[mock_image_sync])
mock_contree_sync.images.pull = MagicMock(return_value=mock_image_sync)

patch('contree_sdk.ContreeSync', return_value=mock_contree_sync).start()
```
-->
```python
import stat

from contree_sdk import ContreeSync
from contree_sdk.utils.objects.file import UploadFileSpec

def main():
    # Create client
    contree = ContreeSync(token='real-contree-token')

    # list images
    images = contree.images()

    # Pulling existing image
    ubuntu_image = contree.images.pull("ubuntu:latest")

    # Pulling image from a remote registry
    busybox_image = contree.images.pull("docker://docker.io/busybox:latest")

    # running command
    result0 = ubuntu_image.run(
        command='/app.sh',
        args=('arg1', 'arg2'),
        stdin='input',
        env=dict(http_proxy='http://10.20.30.40:1234'),
        files=[
            UploadFileSpec(source='/local/files/app.sh', mode=stat.S_IXUSR),
            UploadFileSpec(source='/local/files/data_ver1.csv', path='/data.csv'),
        ]
    ).wait()
    print(result0.stdout)
    print(result0.stderr)

    # running next command
    result1 = result0.run(shell='echo output.csv | grep something').wait()

    # getting files and directories by path
    items = result1.ls('files/path')
    print(len(items))

    # iterating through files and directories by path
    for item in result1.ls('~'):
        print(item.name, item.is_dir)
        if item.is_file:
            # download file
            item.download('/local/files/downloaded/')

    # using session
    session = busybox_image.session()
    session.run(
        command='/bin/app',
        files=[UploadFileSpec(source='/local/files/app', path='/bin/app', mode=stat.S_IXUSR)]
    ).wait()
    res = session.run(command='cat', args=('result.txt',)).wait()
    print(res.stdout)

    # downloading file from session
    session.download('/tmp/log.jsonl', '/local/logs/session_1.log')

    # or simply reading from file
    content = session.read('/tmp/log.jsonl')
    print(content.decode())

main()
```

</details>

---

## 🧠 Core Concepts

### Sessions and Versioning

> [!NOTE]
> Sessions automatically track image versions after each command execution.

A **session** is essentially an image whose version automatically updates after each command execution. When you run commands, you're not modifying the original image - instead, each command creates a new version of the image with your changes applied.

<!-- name: test_sessions_versioning
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

mock_result = MagicMock()
mock_result.run = AsyncMock(return_value=MagicMock())

mock_image = MagicMock()
mock_image.run = AsyncMock(return_value=mock_result)
mock_image.session = MagicMock(return_value=MagicMock(
    run=AsyncMock(return_value=MagicMock())
))

mock_contree = MagicMock()
mock_contree.images = MagicMock()
mock_contree.images.pull = AsyncMock(return_value=mock_image)

patch('contree_sdk.Contree', return_value=mock_contree).start()
```
-->
```python
import asyncio
from contree_sdk import Contree

async def amain():
    contree = Contree(token='my-token')

    # Each command creates a new image version
    image = await contree.images.pull("ubuntu:latest")        # ubuntu:latest
    result1 = await image.run(shell="apt update")             # some-uuid
    result2 = await result1.run(shell="apt install python3") # another-uuid

    # Sessions work the same way
    session = image.session()                     # ubuntu:latest
    await session.run(shell="touch /app/file1.txt")    # some-uuid
    await session.run(shell="echo 'hello' > /app/file1.txt") # another-uuid

asyncio.run(amain())
```

### Subprocess-like interface

Any session can provide Subprocess-like interface

> [!WARNING]
> **Async version**: Subprocess-like interface is not yet implemented for async clients. Use sync clients for this functionality.

<details open>
<summary>🔁 Sync examples</summary>

Running command
<!-- name: test_subprocess_cat
```python
from unittest.mock import MagicMock

mock_proc = MagicMock()
mock_proc.communicate = MagicMock(return_value=("a\nb\nc\n", ""))

session = MagicMock()
session.popen = MagicMock(return_value=mock_proc)
```
-->
```python
proc = session.popen(
    ["cat"],
    text=True,
)
stdout, stderr = proc.communicate("a\nb\nc\n")
```

Shell example
<!-- name: test_subprocess_shell
```python
from unittest.mock import MagicMock

mock_proc = MagicMock()
mock_proc.wait = MagicMock(return_value=0)
mock_proc.stdout = "hello\ntotal 0\n"

session = MagicMock()
session.popen = MagicMock(return_value=mock_proc)
```
-->
```python
import subprocess

proc = session.popen(
    "echo hello && ls -la",
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
returncode = proc.wait()
print(proc.stdout)
```

</details>

### Stable image UUID

Basically one UUID refers to one state of FS, so in case if after running commands on the image, no FS changes are detected, UUID stays the same.

<!-- name: test_stable_uuid
```python
from unittest.mock import MagicMock
from uuid import uuid4

same_uuid = uuid4()

mock_result0 = MagicMock()
mock_result0.uuid = same_uuid
mock_result0.run = MagicMock(return_value=MagicMock(wait=MagicMock(return_value=MagicMock(uuid=same_uuid))))

mock_pending = MagicMock()
mock_pending.wait = MagicMock(return_value=mock_result0)

image = MagicMock()
image.run = MagicMock(return_value=mock_pending)
```
-->
```python
result0 = image.run('echo CHANGES > file.txt').wait()
result1 = result0.run('sleep 5').wait()

assert result1.uuid == result0.uuid
```

### Async/sync clients and objects

Basically every object that is produced by async client is async-friendly and every object is produced by sync client is sync friendly.
For example

<!-- name: test_async_sync_clients
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

mock_async_image = MagicMock()
mock_async_image.run = AsyncMock(return_value=MagicMock())

mock_contree_async = MagicMock()
mock_contree_async.images = AsyncMock(return_value=[mock_async_image])

mock_sync_image = MagicMock()
mock_sync_image.run = MagicMock(return_value=MagicMock(wait=MagicMock()))

mock_contree_sync = MagicMock()
mock_contree_sync.images = MagicMock(return_value=[mock_sync_image])

patch('contree_sdk.Contree', return_value=mock_contree_async).start()
patch('contree_sdk.ContreeSync', return_value=mock_contree_sync).start()
```
-->
```python
import asyncio
from contree_sdk import Contree, ContreeSync

async def amain():
    contree_async = Contree(token='my-token')

    # async client produces async-friendly images objects, so they can be used in async code
    images = await contree_async.images()
    await images[0].run(shell='some command')

asyncio.run(amain())

contree_sync = ContreeSync(token='my-token')

# while sync client produces sync-friendly images objects, so they can be used in sync code
images = contree_sync.images()
images[0].run(shell='some command').wait()
```

> [!NOTE]
> In sync Image-like object `.wait()` method is used as opposed to await keyword in async version

---

## ⚙️ Advanced Usage

### Client configuration
You can create configuration object and use it later in client
<!-- name: test_client_configuration
```python
from unittest.mock import MagicMock, patch

patch('contree_sdk.Contree', MagicMock()).start()
patch('contree_sdk.ContreeSync', MagicMock()).start()
```
-->
```python
from contree_sdk.config import ContreeConfig, ContreeEndpoint
from contree_sdk import Contree, ContreeSync

config = ContreeConfig(
    token='my-token',
    base_url=ContreeEndpoint.STAGE,  # or 'https://contree.host.com'
    transport_timeout=10.0,  # timeout for transport operations
)

client_async = Contree(config)
client = ContreeSync(config)
```

### Objects reusing

You can preconfigure run and then reuse it, for example:
<!-- name: test_objects_reusing
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

mock_image = MagicMock()
mock_image.run = MagicMock(return_value=AsyncMock(return_value=MagicMock())())

mock_contree = MagicMock()
mock_contree.images = MagicMock()
mock_contree.images.pull = AsyncMock(return_value=mock_image)

patch('contree_sdk.Contree', return_value=mock_contree).start()
```
-->
```python
import asyncio
from contree_sdk import Contree

async def amain():
    contree = Contree(token='my-token')
    image = await contree.images.pull("ubuntu:latest")

    # preconfigure a run that generates random string and writes to file
    preconfigured_run = (
        image.run(shell='echo $RANDOM > /tmp/random.txt')
    )

    # reuse it multiple times
    result1 = await preconfigured_run
    result2 = await preconfigured_run
    result3 = await preconfigured_run

    # each execution will generate different uuid, because each result is gonna be unique

asyncio.run(amain())
```

### File uploading

> [!WARNING]
> This is a low-level API. Use only if you are deeply familiar with Contree architecture and need direct file management.
> For most use cases, prefer `files` parameter in `.run()` method.

<!-- name: test_file_uploading
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

mock_file = MagicMock()
mock_file.uuid = uuid4()

mock_contree = MagicMock()
mock_contree.files = MagicMock()
mock_contree.files.upload = AsyncMock(return_value=mock_file)

patch('contree_sdk.Contree', return_value=mock_contree).start()
```
-->
```python
import asyncio
from contree_sdk import Contree

async def amain():
    contree = Contree(token='my-token')

    # upload file
    file = await contree.files.upload('/some/local/file.txt')
    print(file.uuid)

asyncio.run(amain())
```

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
