"""Canonical directory-name constants for the architecture repository structure.

Import these instead of bare string literals so that a directory rename is a
one-line change rather than a grep-and-replace across the entire codebase.
"""

ENGAGEMENT_REPO = "architecture-repository"
MODEL = "model"
DOCS = "docs"
PROJECTS = "projects"  # model-project group containers: PROJECTS/<slug>/MODEL/...
DIAGRAM_CATALOG = "diagram-catalog"
DIAGRAMS = "diagrams"  # subdirectory within DIAGRAM_CATALOG/
RENDERED = "rendered"  # subdirectory within DIAGRAMS/ — excluded from indexing
ARCH_REPO = ".arch-repo"
ARCH_DOC_SCHEMATA = "documents"  # subdirectory within ARCH_REPO/ — document type JSON schemas
