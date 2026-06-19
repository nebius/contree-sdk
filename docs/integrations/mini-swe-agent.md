---
icon: robot
---

# Mini-SWE-Agent Integration

[Mini-SWE-Agent](https://mini-swe-agent.com/latest/) is a lightweight software engineering agent.
The ConTree integration enables it to execute code in isolated, reproducible containers. Every command in Mini-SWE-Agent is executed in a fresh shell session, which makes it perfectly suitable for ConTree.

Integration is available via [ContreeEnvironment](https://mini-swe-agent.com/latest/reference/environments/contree/) starting from [mini-swe-agent v2.2.0](https://github.com/SWE-agent/mini-swe-agent/releases/tag/v2.2.0).

## Using ContreeEnvironment

```{literalinclude} ../../examples/mini_swe_agent/mini_swe_agent_basic.py
:language: python
:linenos:
```

## Running with SWE-bench

### Setup

1. Install the dependencies:

   ```bash
   pip install "mini-swe-agent[contree]"
   ```

2. Set up Nebius IAM token and base URL:

   ```bash
   export NEBIUS_API_KEY="your-nebius-iam-token"
   export NEBIUS_PROJECT_ID="your-project-id"
   export CONTREE_BASE_URL="your-given-base-url-for-contree"
   ```

### Usage

Run mini-swe-agent like with any other environment:

```bash
mini-extra swebench \
    --subset verified \
    --split test \
    --workers 100
    --environment-class contree
```

It can be specified both through cli parameter or by setting `environment_class` to `contree` in your swebench.yaml config
