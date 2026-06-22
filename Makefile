.PHONY: rtd-dev type-check type-check-ignore type-check-docs type-check-docs-ignore

DOCS_DIR := docs

rtd-dev:
	uv run sphinx-autobuild $(DOCS_DIR) $(DOCS_DIR)/_build/html

docs-mintlify-clean:
	rm -rf $(DOCS_DIR)/_build/mintlify

docs-mintlify-build:
	uv run --extra docs sphinx-build -b mintlify $(DOCS_DIR) $(DOCS_DIR)/_build/mintlify

docs-mintlify:
	$(MAKE) docs-mintlify-clean
	$(MAKE) docs-mintlify-build

type-check:
	uv run --all-extras python scripts/ty_baseline.py check

type-check-ignore:
	uv run --all-extras python scripts/ty_baseline.py update

type-check-no-baseline:
	uv run --all-extras ty check

type-check-docs:
	uv run --all-extras python scripts/ty_baseline.py --config-file tests/unit/docs/ty.docs.toml --baseline-path tests/unit/docs/baseline.yaml check tests/unit/docs/_tmp

type-check-docs-ignore:
	uv run --all-extras python scripts/ty_baseline.py --config-file tests/unit/docs/ty.docs.toml --baseline-path tests/unit/docs/baseline.yaml update tests/unit/docs/_tmp
