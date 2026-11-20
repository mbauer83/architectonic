"""A diagram write refused because a workspace-scoped record's id is not of the form its type asks for.

One refusal for create and edit, which stated it twice and differed only in what a new diagram has
no answer for: the ids already committed, and a path.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from src.application.verification._workspace_identity_rules import (
    committed_workspace_entity_ids,
    validate_workspace_entity_ids,
)
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.config import settings

from .types import WriteResult


def refused_for_workspace_ids(
    *,
    verifier: ArtifactVerifier,
    diagram_type: str,
    entities: object,
    stored_frontmatter: dict | None,
    path: Path,
    artifact_id: str,
    verified_as: str,
    issue_location: str,
    warnings: list[str],
) -> WriteResult | None:
    """The refusal for *entities* whose new workspace ids are malformed, or None where none is.

    *stored_frontmatter* is the diagram as committed, whose ids are not new; None for a diagram being
    created, where every id is.
    """
    if not isinstance(entities, Mapping):
        return None
    try:
        module = verifier.runtime_catalogs.diagram_types.find_diagram_type(diagram_type)
    except Exception:  # noqa: BLE001
        module = None
    if module is None:
        return None
    committed = committed_workspace_entity_ids(stored_frontmatter, module) if stored_frontmatter is not None else None
    errors = validate_workspace_entity_ids(dict(entities), module, committed_ids=committed)
    if not errors or not settings.datatype_type_references_blocking():
        return None
    return WriteResult(
        wrote=False, path=path, artifact_id=artifact_id, content=None, warnings=warnings,
        verification={
            "path": verified_as, "file_type": "diagram", "valid": False,
            "issues": [
                {"severity": "error", "code": "E335-fmt", "message": message, "location": issue_location}
                for message in errors
            ],
        },
    )
