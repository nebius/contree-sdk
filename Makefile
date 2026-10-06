.PHONY: rtd-dev type-check type-check-ignore test-docs

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


test-docs:
	uv run --extra dev pytest -m markdown README.md docs
