# 📦 Contree SDK

> [!IMPORTANT]
> **Disclaimer**: This SDK is currently in development. All code examples and usage patterns shown below are conceptual and do not reflect the final implementation. The API is subject to change.

## Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Core Concepts](#-core-concepts)
  - [Sessions and Versioning](#sessions-and-versioning)
  - [Async/sync clients and objects](#asyncsync-clients-and-objects)
- [Advanced Usage](#-advanced-usage)
  - [Client configuration](#client-configuration)
  - [Command and other run parameters](#command-and-other-run-parameters)
  - [Disposable containers](#disposable-containers)
  - [Multiple commands chaining](#multiple-commands-chaining)
  - [Forwarding output to IO objects](#forwarding-output-to-io-objects)
  - [Forwarding input from IO objects](#forwarding-input-from-io-objects)
  - [File uploading](#file-uploading)
  - [History browsing](#history-browsing)
  - [Tree browsing](#tree-browsing)
  - [Revert](#revert)
- [CLI shell usage](#-cli-shell-usage)

---

## 📥 Installation

In order to install contree run `pip install contree-sdk`

If you want to use a specific transport (for example, httpx), run `pip install contree-sdk[httpx]`

Optional extras allow you to install dependencies for specific transports or integrations. For example, httpx enables asynchronous HTTP support.

If you are planning to use it as shell, install `shell` extra: `pip install contree-sdk[shell]`

---

## 🚀 Quick Start

<details open>
<summary>🔀 Async Example</summary>

```python
import asyncio
import stat

from contree_sdk import Contree

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
    result0 = await (
        ubuntu_image.command('app.sh').args('arg1', 'arg2')
        .stdin('input')
        .env(http_proxy='http://10.20.30.40:1234')
        .add_file('/local/files/app.sh', mode=stat.S_IXUSR)
        .add_file('/local/files/data_ver1.csv', '/data.csv')
        .tag('ubuntu-result0:latest')
    )
    print(result0.stdout)
    print(result0.stderr)
    
    # running next command
    result1 = await result0.shell('echo output.csv | grep something')
    
    # getting files and directories by path
    items = await result1.ls('files/path')
    print(len(items))
    
    # iterating through files and directories by path
    async for item in result1.ls('~'):
        print(item.name, item.is_dir)
        if item.is_file:
            # download file
            await item.download('/local/files/downloaded/')
    
    files = await result1.files('/bin')
    print(files)
    
    # using session
    session = await busybox_image.session()
    await (
        session.command('/bin/app')
        .add_file('/local/files/app', 'bin/app', mode=stat.S_IXUSR)
    )
    res = await session.command('cat result.txt')
    print(res.stdout)
    
    # downloading file from session
    await (
        session.file('/tmp/log.jsonl')
        .download('/local/logs/session_1.log')
    )
    

asyncio.run(amain())
```

</details>

<details>
<summary>🔁 Sync Example</summary>

```python
import stat

from contree_sdk import ContreeSync

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
    result0 = (
        ubuntu_image.command('app.sh').args('arg1', 'arg2')
        .stdin('input')
        .env(http_proxy='http://10.20.30.40:1234')
        .add_file('/local/files/app.sh', mode=stat.S_IXUSR)
        .add_file('/local/files/data_ver1.csv', '/data.csv')
    ).wait()
    print(result0.stdout)
    print(result0.stderr)
    
    # running next command
    result1 = result0.command('echo output.csv | grep something').wait()
    
    # getting files and directories by path
    items = result1.ls('files/path')
    print(len(items))
    
    # iterating through files and directories by path
    for item in result1.ls('~'):
        print(item.name, item.is_dir)
        if item.is_file:
            # download file
            item.download('/local/files/downloaded/')
    
    files = result1.files('/bin')
    print(files)
    
    # using session
    session = busybox_image.session()
    (
        session.command('/bin/app')
        .add_file('/local/files/app', 'bin/app', mode=stat.S_IXUSR)
    ).wait()
    res = session.run('cat result.txt').wait()
    print(res.stdout)
    
    # downloading file from session
    session.file('/tmp/log.jsonl').download('/local/logs/session_1.log')
    
    
main()
```

</details>

---

## 🧠 Core Concepts

[//]: # (todo discuss about .wait for sync)
[//]: # (todo discuss about memory usage in parents/children)
[//]: # (todo discuss about persistent env or cwd)

### Sessions and Versioning

> [!NOTE]
> Sessions automatically track image versions after each command execution.

A **session** is essentially an image whose version automatically updates after each command execution. When you run commands, you're not modifying the original image - instead, each command creates a new version of the image with your changes applied.

```python
# Each command creates a new image version
image = await contree.images.pull("ubuntu:latest")        # ubuntu:latest
result1 = await image.run("apt update")             # some-uuid 
result2 = await result1.run("apt install python3") # another-uuid

# Sessions work the same way
session = image.session()                     # ubuntu:latest
res0 = await session.run("touch /app/file1.txt")    # some-uuid 
res1 = await session.run("echo 'hello' > /app/file1.txt") # another-uuid

assert session.current == res1
assert session.parent == res0
```

### Stable image UUID

Basically one UUID refers to one state of FS, so in case if after running commands on the image, no FS changes are detected, UUID stays the same.

```python
result0 = image.run('echo CHANGES > file.txt').wait()
result1 = result0.run('sleep 5').wait()

assert result1.uuid == result0.uuid
assert result1.uuid == result1.parent.uuid

assert result0.changed == True
assert result1.changed == False

```

### Async/sync clients and objects

Basically every object that is produced by async client is async-friendly and every object is produced by sync client is sync friendly.
For example

```python
from contree_sdk import Contree
contree_async = Contree(token='my-token')

# async client produces async-friendly images objects, so they can be used in async code
images = await contree_async.images()
await images[0].run('some command')

from contree_sdk import ContreeSync
contree_sync = ContreeSync(token='my-token')

# while sync client produces sync-friendly images objects, so they can be used in sync code
images = contree_sync.images()
images[0].run('some command').wait()
```

> [!NOTE]
> In sync Image-like object `.wait()` method is used as opposed to await keyword in async version

---

## ⚙️ Advanced usage

[//]: # (todo cancelling on Ctrl+C)
[//]: # (todo add grep example)

### Client configuration
You can create configuration object and use it later in client
```python
from contree_sdk.config import ContreeConfig, ContreeEndpoints
from contree_sdk.transport import HttpxTransport
from contree_sdk import Contree, ContreeSync

config = ContreeConfig(
    token='my-token',
    base_url=ContreeEndpoints.STAGE,  # or 'https://contree.host.com'
    transport=HttpxTransport,  # transport backend that will be used to connect with the server
)

client_async = Contree(config)
client = ContreeSync(config)
```

### Command and other run parameters

<details open>
<summary>🔀 Async Example</summary>

```python
from contree_sdk.files import CopyFile

# this construction
result0 = await (
    ubuntu_image.command('app.sh').args('arg1', 'arg2')
    .stdin('input')
    .env(http_proxy='http://10.20.30.40:1234')
    .add_file('/local/files/app.sh', mode=stat.S_IXUSR)
    .add_file('/local/files/data_ver1.csv', '/data.csv')
)
# is basically a syntax sugar for this:
result0 = await ubuntu_image.run(
    command='app.sh',
    args=('arg1', 'arg2'),
    stdin='input',
    env=dict(http_proxy='http://10.20.30.40:1234'),
    files=[
        CopyFile('/local/files/app.sh', mode=stat.S_IXUSR),
        CopyFile('/local/files/data_ver1.csv', '/data.csv'),
    ]
)
```

</details>

<details>
<summary>🔁 Sync Example</summary>

```python
from contree_sdk.files import CopyFile

# this construction
result0 = (
    ubuntu_image.command('app.sh').args('arg1', 'arg2')
    .stdin('input')
    .env(http_proxy='http://10.20.30.40:1234')
    .add_file('/local/files/app.sh', mode=stat.S_IXUSR)
    .add_file('/local/files/data_ver1.csv', '/data.csv')
).wait()
# is basically a syntax sugar for this:
result0 = ubuntu_image.run(
    command='app.sh',
    args=('arg1', 'arg2'),
    stdin='input',
    env=dict(http_proxy='http://10.20.30.40:1234'),
    files=[
        CopyFile('/local/files/app.sh', mode=stat.S_IXUSR),
        CopyFile('/local/files/data_ver1.csv', '/data.csv'),
    ]
).wait()
```

</details>

### Shell vs command

The SDK provides two distinct ways to execute commands:

- **`command()`** - Direct program execution 
- **`shell()`** - Shell command execution

<details open>
<summary>🔀 Async Examples</summary>

```python
# run() - direct program execution
result = await image.command('ls').args('-la', '/home')
# Equivalent to: execve("/bin/ls", ["ls", "-la", "/home"], env)

# shell() - shell command interpretation  
result = await image.shell('ls -la /home')
# Equivalent to: execve("/bin/sh", ["sh", "-c", "ls -la /home"], env)

# Pipes and redirects work only with shell()
result = await image.shell('echo "hello world" | grep hello')
result = await image.shell('ls > /tmp/files.txt')

# Shell variables and expansions work only with shell()
result = await image.shell('echo $HOME && echo *.txt')

# run() is safer for user input (no shell injection)
filename = "user_file.txt"  # safe - no interpretation
result = await image.command('cat').args(filename)
```

</details>

<details>
<summary>🔁 Sync Examples</summary>

```python
# run() - direct program execution
result = image.command('ls').args('-la', '/home').run()

# shell() - shell command interpretation
result = image.shell('ls -la /home').run()

# Complex shell commands
result = image.shell('find /etc -name "*.conf" | head -5 | sort').run()

# Multiple commands with &&
result = image.shell('mkdir -p /app && cd /app && git clone https://github.com/user/repo.git').run()
```

</details>

> [!TIP]
> Use `shell()` for complex commands with pipes, redirects, and shell features. Use `command()` for simple commands and when security is important.

### Env parameter

Env can be passed both as kwargs parameters and as a dict object:

```python
image.env(VAR='VALUE', http_proxy='http://10.20.30.40:1234')
# is same as
image.env({'VAR': 'VALUE', 'http_proxy': 'http://10.20.30.40:1234'})
# or you can even use both at the same time
image.env({'VAR': 'VALUE'}, http_proxy='http://10.20.30.40:1234')
```


### Disposable containers
You can add `.disposable()` to the chain or as run parameter to make the container disposable. 
It means it deletes itself right after executing, leaving only the result.

```python
res = image.disposable().run('one time thing').wait()
# OR
res = image.run('one time thing', disposable=True).wait()
```


### Multiple commands chaining

You can chain multiple commands in sequence, where each command builds upon the result of the previous one:

```python
# Simple chaining
result = await (
    image.run("apt update")
    .run("apt install -y python3")
    .run("pip install requests")
)

# Parameters apply only to the next run
result1 = await (
    image.env(PATH="/usr/local/bin").stdin("input data").shell("echo $PATH")  # Uses env and stdin
)

result2 = await result1.shell("echo $PATH")  # Clean run, no env/stdin
```

> [!IMPORTANT]
> **Async**: `.run()` queues the command, execution happens on `await`  
> **Sync**: `.run()` queues the command, execution happens on `.wait()`

Each finished `.run()` creates a new image version with changes from that command.

[//]: # (todo to discuss further how to make proper non-wasteful chaining)

### Objects reusing

You can preconfigure run and then reuse it, for example:
```python
# preconfigure a run that generates random string and writes to file
preconfigured_run = (
    image.shell('echo $RANDOM > /tmp/random.txt')
)

# reuse it multiple times
result1 = await preconfigured_run
result2 = await preconfigured_run
result3 = await preconfigured_run

# each execution will generate different uuid, because each result is gonna be unique

# this way all results will have the same parent:
assert result1.parent == result2.parent == result3.parent == image
```

### Forwarding output to IO objects
You can forward stdout/stderr output to IO-like objects and files

```python
import sys
import io

stdout_buffer = io.StringIO()
res = image.stdout_to(stdout_buffer).stderr_to(sys.stderr).run('some command').wait()
# it will output stdout of run to `stdout_buffer` and stderr to `sys.stderr`

# stderr/stdout settings are persistent after run
res1 = res.run('another command').wait()
# will still output stdout of run to `stdout_buffer` and stderr to `sys.stderr`

# this however will not
res_other = image.run('third command').wait()

# BytesIO also can be used
bytes_buffer = io.BytesIO()
image.stdout_to(bytes_buffer)

# you can also use files
res = image.stderr_to('/local/files/error.log').run('failing command').wait()
```

### Forwarding input from IO objects
Similarly, you can forward input from IO-like object

```python
import io
import sys

from pathlib import Path

# from sys.stdin
await image.stdin(sys.stdin).run('some-command')

# from file
await image.stdin(Path("input.txt")).run('some-command')

# from bytes IO object
bytes_buffer = io.BytesIO()
bytes_buffer.write(b"binary data\x00\x01\x02")
bytes_buffer.seek(0)
await image.stdin(bytes_buffer).shell('hexdump -C')

# by the way, you can just pass bytes as stdin
await image.stdin(b"binary data\x00\x01\x02").shell('hexdump -C')
```

> [!NOTE]
> It will run command only after finishing reading from IO object. It cannot run and read simultaneously!

### File uploading

> [!WARNING]
> This is a low-level API. Use only if you are deeply familiar with Contree architecture and need direct file management. 
> For most use cases, prefer `.add_file()` method on images and sessions.

```python
# check file existence
if await contree.files.exists('some-uuid'):
    print('File exists')

# upload file
file = await contree.files.upload('/some/local/file.txt')
print(file.uuid)
```

### History browsing

Since server doesn't store info about which containers were parents for which, it is implemented on client side. 
It means that once you delete `Contree` (or `ContreeSync` object), the history (as wel as tree) erases itself.

```python
result_image = await busybox_image.run('some command')
result_image2 = await result_image.run('another command')

assert result_image2.parent == result_image
assert result_image.parent == busybox_image

for parent in result_image2.parents:
    assert parent in {result_image, result_image2}
```

### Tree browsing

It's basically same as browsing parents, but for children, except that each parent container can have multiple children ones.

```python
result_image = await busybox_image.run('some command')
result_image2 = await result_image.run('another command')

result_image_new = await busybox_image.run('some another command')

assert busybox_image.children == [result_image, result_image_new]
assert result_image.children == [result_image2]
assert busybox_image.tree == [result_image, result_image_new, result_image2]
```

### Revert

```python
image = await contree.images.pull("ubuntu:latest")
session = image.session()  

await session.run('command1')
result2 = await session.run('command2')

# now session points to the result of 'command2'
# but if we revert it
session.revert()
# it will actually point to the result of 'command1'

assert session.parent == image
assert session.children == [result2]
```

---

## 🐚 CLI shell usage

Contree SDK provide support for shell

```console
$ contree-sdk.shell --token my-token
contree> pull busybox:latest
Pulling image busybox:latest... done

contree[busybox:latest]> env NAME=World
Run parameters are:
env: NAME=World

contree[busybox:latest]> add file /some/local/file
Run parameters are:
env: NAME=World
files:
    /some/local/file

contree[busybox:latest]> run echo "Hello, $NAME!"
Running...
Hello, World!

contree[bebecde7-01cd-4abc-a0f1-f97d0bc38336]> revert
Reverted to busybox:latest

contree[busybox:latest]> exit
Bye 👋
```

Run `contree-sdk.shell --help` to know more about usage