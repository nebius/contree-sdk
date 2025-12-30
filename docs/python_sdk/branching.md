# Branching Workflows

One of Contree's most powerful features is the ability to branch execution flows from a single base filesystem state (a snapshot of all files and directories in a container at a specific point in time). This is similar to Git branches, but for container execution states.

## Why Branching Matters

Without Contree, running the same operations twice (like installing packages, creating files, or compiling code) requires rebuilding the entire filesystem state from scratch each time. Contree captures the exact filesystem state after each command, making it reproducible and allowing you to branch from that exact state.

## Simple Branching Example

This example demonstrates creating a parent state with a random value, then branching into multiple child states from that fixed parent:

````{tab} Async
```{literalinclude} ../../examples/branching/branching_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImage.run` for full API reference.
````

````{tab} Sync
```{literalinclude} ../../examples/branching/branching_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImageSync.run` for full API reference.
````

**Key Points:**

- The `child` state contains a random value that would be different on each execution without Contree
- All three grandchildren start from the exact same `child` state (same random value)
- Each grandchild branches independently, creating different execution paths

## Advanced Branching Patterns

For more complex scenarios with multiple branching strategies:

````{tab} Async
```{literalinclude} ../../examples/branching/branching_basic.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.sdk.objects.image.ContreeImage` for full API reference.
````

````{tab} Sync
```{literalinclude} ../../examples/branching/branching_basic_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.sdk.objects.image.ContreeImageSync` for full API reference.
````

## Use Cases

Branching is particularly useful for:

- **Testing multiple scenarios**: Run different operations from the same starting state
- **Reproducible randomness**: Capture random/non-deterministic operations and branch from them
- **Parallel execution paths**: Execute different workflows from a common checkpoint
- **Version control for execution**: Create branches like Git for different execution flows
