# Import-only: both examples also need a real LLM call, too heavy to fake here.
import inspect

import pytest


pytest.importorskip("deepagents", reason="langchain integration needs deepagents (Python >= 3.11)")
pytest.importorskip("minisweagent", reason="mini-swe-agent integration needs the `mini-swe-agent` package")

from examples.langchain.langchain_basic import main as langchain_main
from examples.mini_swe_agent.mini_swe_agent_basic import main as mini_swe_agent_main


def test_langchain_basic_example_imports():
    assert inspect.iscoroutinefunction(langchain_main)


def test_mini_swe_agent_basic_example_imports():
    assert callable(mini_swe_agent_main)
