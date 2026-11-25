"""A new diagram written from a composition: rendered once, given an id, and created through the write path.

What the REST create and a candidate's *Save as diagram* share, so a picture saved from a candidate is
created as every diagram is: the same rendering (`render_composition`), the same id allocation and the
same verified write (`create_diagram`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write import prefix_for_diagram_type
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.diagram_composition import DiagramComposition, render_composition
from src.infrastructure.write.artifact_write.diagram import create_diagram
from src.infrastructure.write.artifact_write.types import WriteResult


@dataclass(frozen=True, slots=True)
class DiagramFiling:
    """What the operation decides about a new diagram, beside what it draws: where it is filed, and its header."""

    group: str = UNCATEGORIZED
    keywords: list[str] | None = None
    layout: dict[str, Any] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = field(default=None)


def create_composed_diagram(
    body: DiagramComposition, filing: DiagramFiling, *, repo: Any, repo_root: Path, verifier: ArtifactVerifier,
    clear_caches: Callable[[Path], None], dry_run: bool,
) -> WriteResult:
    """Create a diagram drawing *body*, filed as *filing* says. Raises `CompositionRefused` for a composition
    the caller has to correct, and `ValueError` for anything the write refuses."""
    composed = render_composition(body, repo=repo, repo_root=repo_root)
    return create_diagram(
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_caches,
        diagram_type=body.diagram_type, name=body.name, group=filing.group, puml=composed.puml,
        artifact_id=get_default_allocator().allocate(
            prefix=prefix_for_diagram_type(body.diagram_type), name_hint=body.name,
        ),
        keywords=filing.keywords, diagram_entities=composed.diagram_entities,
        diagram_connections=composed.diagram_connections, entity_ids_used=composed.entity_ids_used,
        connection_ids_used=composed.connection_ids_used, authored_groupings=body.authored_groupings,
        layout=filing.layout, version=filing.version, status=filing.status, last_updated=None, tlp=filing.tlp,
        connection_inference="none", bindings=composed.conn_bindings or None, viewpoint=filing.viewpoint,
        dry_run=dry_run,
    )
