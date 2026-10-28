.PHONY: rtd-dev type-check test-docs

DOCS_DIR := docs

rtd-dev:
	$(MAKE) -C $(DOCS_DIR) serve

docs-mintlify-clean:
	rm -rf $(DOCS_DIR)/_build/mintlify

docs-mintlify-build:
	$(MAKE) -C $(DOCS_DIR) mintlify

docs-mintlify:
	$(MAKE) docs-mintlify-clean
	$(MAKE) docs-mintlify-build

type-check:
	uv run --all-extras ty check


test-docs:
	$(MAKE) -C $(DOCS_DIR) test
