:icon: robot

LangChain Sandbox
=================

Requires the ``contree-sdk[langchain]`` extra. See
:doc:`../../integrations/langchain` for setup and a full usage example.

``ContreeSandbox`` implements deepagents' ``execute()``, ``upload_files()``,
``download_files()`` and ``id`` on top of a ``ContreeSession``; the many
other ``BaseSandbox`` methods it inherits (``ls``, ``read``, ``write``,
``grep``, ...) are deepagents' own defaults, documented in `deepagents
<https://docs.langchain.com/oss/python/deepagents/backends/sandbox>`_ rather
than here.

.. automodule:: contree_sdk.langchain
   :members: ContreeSandbox
   :undoc-members:
   :member-order: bysource
