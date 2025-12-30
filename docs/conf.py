from datetime import datetime
from importlib.metadata import version as get_version


project = "Contree"
copyright = f"{datetime.now().year}, Nebius"  # noqa: A001
author = "Nebius"
version = release = get_version("contree-docs")

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.duration",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx_copybutton",
    "sphinx_inline_tabs",
    "sphinxcontrib.log_cabinet",
]

autosummary_generate = True
autosummary_generate_overwrite = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "_autosummary"]


html_theme = "furo"
html_title = project

autodoc_typehints = "both"
set_type_hints_directive = True


# -- MyST configuration -----------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "dollarmath",
    "fieldlist",
    "html_admonition",
    "html_image",
    "linkify",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]

myst_heading_anchors = 3

# -- Source file suffixes ---------------------------------------------------

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Master document
master_doc = "index"
