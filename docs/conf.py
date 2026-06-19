from datetime import datetime
from importlib.metadata import version as get_version


project = "ConTree SDK"
copyright = f"{datetime.now().year}, Nebius"  # noqa: A001
author = "Nebius"
version = release = get_version("contree-sdk")

extensions = [
    "myst_parser",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.duration",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_inline_tabs",
    "sphinxcontrib.log_cabinet",
    "sphinx_mintlify_output",
]

autosummary_generate = True
autosummary_generate_overwrite = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "_autosummary"]


html_theme = "furo"
html_title = f"{project} Documentation"
html_logo = "_static/logo.svg"


autodoc_typehints = "signature"
autoclass_content = "class"
set_type_hints_directive = True

simplify_optional_unions = False

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

# -- Mintlify output --------------------------------------------------------

mintlify_docs_json = {
    "name": "ConTree SDK",
    "theme": "mint",
    "logo": {"light": "static/logo.svg", "dark": "static/logo.svg"},
}
