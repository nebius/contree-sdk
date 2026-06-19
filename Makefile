.PHONY: rtd-dev type-check-docs type-check-docs-ignore

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

type-check-docs:
	basedpyright tests/unit/docs/_tmp

type-check-docs-ignore:
	basedpyright --writebaseline tests/unit/docs/_tmp
