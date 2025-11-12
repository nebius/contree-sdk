# Contree SDK

> **⚠ Disclaimer**: This SDK is currently in development. All code examples and usage patterns shown below are conceptual and do not reflect the final implementation. The API is subject to change.

## Installation

```bash
pip install contree-sdk
```

## Quick Start

*async example*
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
    )
    print(result0.stdout)
    print(result0.stderr)
    
    # running next command
    result1 = await result0.command('echo output.csv | grep something')
    
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

*sync example*
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
    ).run()
    print(result0.stdout)
    print(result0.stderr)
    
    # running next command
    result1 = result0.command('echo output.csv | grep something').run()
    
    # getting files and directories by path
    items = result1.ls('files/path')
    print(len(items))
    
    # iterating through files and directories by path
    async for item in result1.ls('~'):
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
    ).run()
    res = session.run('cat result.txt')
    print(res.stdout)
    
    # downloading file from session
    session.file('/tmp/log.jsonl').download('/local/logs/session_1.log')
    
    
main()
```

[//]: # (todo think about how in sync should be called, with or without `wait&#40;&#41;`)
[//]: # (todo stdout to io objects, like stdout or BytesIO)

## Advanced usage

### Client configuration

### Command and other run parameters
### Multiple commands chaining
### Forwarding output to IO objects
### Forwarding input from IO objects
### File uploading

[//]: # (todo)

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

## Core Concepts

### Sessions and Versioning

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

## CLI shell usage

[//]: # (todo )