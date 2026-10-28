# Develop and test the documentation

User scenarios live in Markdown. `markdown-pytest` collects and executes those
blocks during the same pytest run as the SDK tests. Changes to an example therefore
change the tested program.

## Run the checks

From the repository root:

```bash
uv sync --extra dev --extra docs
uv run pytest
make -C docs test
make -C docs check
```

The pytest command runs the standard suite, including documentation. The `test`
target selects Markdown scenarios. SDK e2e tests are outside the default suite;
transport e2e coverage belongs to `contree-client` and is not a gate for these guides.

From `docs/`, use `make html` to build HTML in `_build/html` or `make serve` to
preview it with live reload at <http://127.0.0.1:8000>. Use `make clean` to remove
build output, `make mintlify` for Mintlify output, and `make help` to list targets.
Use `make check` for an HTML build that treats Sphinx warnings as errors.

Set `BUILDDIR` to change the output directory, `SPHINXOPTS` to change Sphinx options,
or `HOST` and `PORT` to configure the preview server. For example:

```bash
make -C docs html BUILDDIR=/tmp/contree-sdk-docs
make -C docs serve PORT=8080
```

Run Semgrep in its own tool environment, as the security workflow does. Its
dependencies conflict with the agent integration dependencies:

```bash
uv tool run --from semgrep==1.168.0 semgrep ci
```

The fixtures replace client construction with `contree_client.testing` clients.
They provide explicit API outcomes; session logic, operation handling, memory stores,
and SQLite stores remain real. Check both user-visible results and transport calls.
These tests do not claim to execute a remote shell or verify server implementation.

## Add a scenario next to its explanation

Put a `name` comment directly above each Python fence. Keep the program visible,
including required imports. Related blocks can share a name and execution namespace.
Use `name: async test_example` for a block with top-level `await` or `async with`.

Request `doc_api` to get isolated clients, environment variables, and a temporary
working directory. Add the desired responses in a hidden block. Add assertions
in another hidden block with the same test name. Fixtures live in
`tests/docs_fixtures.py`.

Use a unique test name within the page unless blocks form one scenario. The
coverage check rejects uncollected Python fences and executable `literalinclude`
examples, so a new scenario cannot silently fall out of the regular suite.
Do not mark a scenario as skipped merely because its API response is inconvenient
to model. Optional integrations may request their availability fixture.

## Keep tests useful

For a saved run, verify the selected image and history in addition to output.
For a file upload, verify the source bytes, destination, and download image.
For error handling, inject the error and verify recovery or cleanup. A canned
response alone cannot show whether a command was sent correctly.

Build examples prepare files from the Dockerfile and text fences in
{doc}`python_sdk/building-images`, including scenarios on the advanced page.
Do not keep a second copy of the documented program in a Python test or example file.
Non-Python fences, such as installation commands and Dockerfile input, are explanatory
inputs; `markdown-pytest` itself executes Python fences only.

See the [markdown-pytest documentation](https://mosquito.github.io/markdown-pytest/)
for split blocks, fixtures, hidden code, async tests, and comment syntax.

## Maintain standalone examples

Keep complete scripts in `examples/sync/` and `examples/async/`, with the same
filename for each pair. Keep short API recipes in Markdown instead of copying them
into scripts.

Each script contains a `test_...` function. The examples collector includes all
Python scripts in the default pytest run and rejects scripts without tests.
The tests execute the script's `__main__` entry point with the same offline client
fixture used by Markdown. Assert requests and observable results, including persisted
state when relevant. A new example must include its test before it can pass CI.

Run just the standalone examples with `uv run pytest examples`.
