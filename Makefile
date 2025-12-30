.PHONY: rtd-dev

DOCS_DIR := docs

rtd-dev:
	uv run sphinx-autobuild $(DOCS_DIR) $(DOCS_DIR)/_build/html
