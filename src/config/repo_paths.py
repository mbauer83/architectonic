"""Re-export canonical repo-layout constants from domain.

Infrastructure callers may continue to import from here; application-layer
callers should import from src.domain.repository.repo_layout directly.
"""

from src.domain.repository.repo_layout import (  # noqa: F401
    ARCH_DOC_SCHEMATA,
    ARCH_REPO,
    DIAGRAM_CATALOG,
    DIAGRAMS,
    DOCS,
    ENGAGEMENT_REPO,
    MODEL,
    PROJECTS,
    RENDERED,
)
