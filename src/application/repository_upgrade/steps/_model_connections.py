"""The files a repository's model records its connections in, for a step that rewrites them.

Where such files sit is `artifact_location`'s to say; what one states as its source is read from its
frontmatter. A step that asks which connections the model holds asks the repository's registry
(`view.registry`), as the verifier does.
"""

from __future__ import annotations

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView
from src.domain.repository.artifact_location import artifact_kind, source_globs
from src.domain.repository.frontmatter import opens_with_frontmatter


def connection_files(view: RepoUpgradeView) -> list[str]:
    """Every file of the repository that records an entity's outgoing connections."""
    globs = source_globs(artifact_kind("connection"))
    return sorted({location for glob in globs for location in view.list_files(glob)})


def recorded_source(content: str) -> str:
    """The `source-entity` a connection file states, as written; "" when it states none."""
    if not opens_with_frontmatter(content):
        return ""
    frontmatter = extract_yaml_block(content)
    return str(frontmatter.get("source-entity") or "").strip() if isinstance(frontmatter, dict) else ""
