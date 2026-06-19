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
	uv run --extra dev python scripts/ty_baseline.py check

type-check-ignore:
	uv run --extra dev python scripts/ty_baseline.py update

type-check-no-baseline:
	uv run --extra dev ty check

type-check-docs:
	uv run --extra dev python scripts/ty_baseline.py check tests/unit/docs/_tmp

type-check-docs-ignore:
	uv run --extra dev python scripts/ty_baseline.py update tests/unit/docs/_tmp
