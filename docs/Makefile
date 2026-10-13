SPHINXBUILD ?= uv run --project .. --extra docs sphinx-build
SPHINXAUTOBUILD ?= uv run --project .. --extra docs sphinx-autobuild
SPHINXOPTS ?=
SOURCEDIR = .
BUILDDIR ?= _build
HOST ?= 127.0.0.1
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help check serve test Makefile

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
	@printf '\nAdditional targets:\n  check     Build HTML and treat warnings as errors\n  serve     Build and serve HTML with live reload\n  test      Run Markdown scenarios in README.md and docs\n  mintlify  Build Mintlify output\n'

check:
	$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) -W --keep-going

serve:
	$(SPHINXAUTOBUILD) $(SPHINXOPTS) --host "$(HOST)" --port "$(PORT)" "$(SOURCEDIR)" "$(BUILDDIR)/html"

test:
	uv run --directory .. --extra dev pytest -m markdown README.md docs

%: Makefile
	$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
