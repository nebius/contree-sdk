.PHONY: rtd-dev type-check-docs type-check-docs-ignore

DOCS_DIR := docs

rtd-dev:
	uv run sphinx-autobuild $(DOCS_DIR) $(DOCS_DIR)/_build/html

type-check-docs:
	basedpyright tests/unit/docs/_tmp

type-check-docs-ignore:
	basedpyright --writebaseline tests/unit/docs/_tmp
