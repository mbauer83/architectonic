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
SCRATCHPADS = "scratchpads"  # SCRATCHPADS/<group-slug>/SCR@….scratchpad.yaml — free-standing
#: Two dots so the kind is readable in a directory listing, and so a glob for scratchpads cannot
#: also match a stray `.yaml` someone dropped beside them. Here rather than on the repository
#: because it is a fact about the layout, and the index scans for it without owning the writing.
SCRATCHPAD_SUFFIX = ".scratchpad.yaml"
