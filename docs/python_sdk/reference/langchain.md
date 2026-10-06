# deepagents sandboxes

Requires Python 3.11+ and the `contree-sdk[langchain]` extra. See
{doc}`../../integrations/langchain` for executable scenarios. Adapters accept the
public executor contracts; they do not require concrete session implementations.
Other inherited `BaseSandbox` tools belong to deepagents.

```{automodule} contree_sdk.langchain
:members: ContreeSandbox, ContreeAsyncSandbox
:inherited-members:
:undoc-members:
:member-order: bysource
```
