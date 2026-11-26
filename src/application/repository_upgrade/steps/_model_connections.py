"""The connections a repository's model records, read for a step from the files that record them.

A step sees one repository through its view and no index, so it reads the model's connections where
they are written: each `.outgoing.md` file, by the owners of its two syntaxes — where such files sit
(`artifact_location`) and the declarations inside one (`connection_declaration`).
"""

from __future__ import annotations

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView
from src.domain.artifact_id import is_entity_id, stable_conn_id
from src.domain.repository.artifact_location import artifact_kind, source_globs
from src.domain.repository.connection_declaration import parse_connection_declarations
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


def model_connection_ids(view: RepoUpgradeView) -> frozenset[str]:
    """The stable id of every connection the repository's model records."""
    recorded: set[str] = set()
    for location in connection_files(view):
        content = view.read_text(location)
        source = recorded_source(content) if content is not None else ""
        if content is None or not is_entity_id(source):
            continue
        recorded.update(
            stable_conn_id(f"{source}---{declaration.target_id}@@{declaration.conn_type}")
            for declaration in parse_connection_declarations(content)
            if is_entity_id(declaration.target_id)
        )
    return frozenset(recorded)
