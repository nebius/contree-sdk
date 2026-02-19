# Mini-SWE-Agent Integration

[Mini-SWE-Agent](https://mini-swe-agent.com/latest/) is a lightweight software engineering agent.
The ConTree integration enables it to execute code in isolated, reproducible containers. Every command in Mini-SWE-Agent is executed in a fresh shell session, which makes it perfectly suitable for ConTree.

Currently, integration is implemented inside our fork and [the pull request](https://github.com/SWE-agent/mini-swe-agent/pull/628) is soon to be merged into [Mini-SWE-Agent](https://mini-swe-agent.com/latest/):

## Using ContreeEnvironment

```{literalinclude} ../../examples/mini_swe_agent/mini_swe_agent_basic.py
:language: python
:linenos:
```

## Running with SWE-bench

Update `config/extra/swebench.yaml`:

```yaml
environment:
  environment_class: contree
  contree_config:
    token: "your-contree-token"

model:
  model_name: "openai/gpt-4"
  cost_tracking: "ignore_errors"
  model_kwargs:
    custom_llm_provider: "openai"
    drop_params: true
    temperature: 0.0
    api_base: "https://api.provider.com/v1/"
    api_key: "your-api-key"
```

Run the benchmark:

```bash
python src/minisweagent/run/extra/swebench.py \
  --subset lite \
  --output results \
  --workers 4 \
  --redo-existing
```
