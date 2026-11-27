"""What the enterprise repository holds once a selection is promoted: the selection, and what it holds already.

Every plan-time closure check asks the same membership questions of the same two sets — the reference
closure of documents and diagrams, and the purpose-line closure of diagrams and viewpoints — so the
answer is built once here and each check asks it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.artifact_id import stable_conn_id, stable_id

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.application.document_links import ResolvedArtifactLink
    from src.application.verification.artifact_verifier import ArtifactRegistry


@dataclass(frozen=True)
class ClosureScope:
    """Membership predicates shared by every per-artifact closure check."""

    set_entity_short: frozenset[str]
    enterprise_entity_short: frozenset[str]
    set_document_ids: frozenset[str]
    enterprise_document_ids: frozenset[str]
    set_diagram_ids: frozenset[str]
    enterprise_diagram_ids: frozenset[str]
    enterprise_connection_short: frozenset[str]

    def entity_satisfied(self, entity_id: str) -> bool:
        short = stable_id(entity_id)
        return (
            short in self.set_entity_short
            or short in self.enterprise_entity_short
            or entity_id.startswith("GAR@")
        )

    def document_satisfied(self, document_id: str) -> bool:
        return document_id in self.set_document_ids or document_id in self.enterprise_document_ids

    def diagram_satisfied(self, diagram_id: str) -> bool:
        return diagram_id in self.set_diagram_ids or diagram_id in self.enterprise_diagram_ids

    def link_satisfied(self, link: "ResolvedArtifactLink") -> bool:
        """Whether the artifact a required link names survives promotion, whatever kind it is."""
        if link.kind == "document":
            return self.document_satisfied(link.artifact_id)
        if link.kind == "diagram":
            return self.diagram_satisfied(link.artifact_id)
        return self.entity_satisfied(link.artifact_id)


def closure_scope(
    *, document_ids: list[str], diagram_ids: list[str], promoted_entity_ids: set[str], registry: "ArtifactRegistry"
) -> ClosureScope:
    """The scope of one promotion: the selected artifacts, and what the enterprise repository holds."""
    return ClosureScope(
        set_entity_short=frozenset(stable_id(e) for e in promoted_entity_ids),
        enterprise_entity_short=frozenset(stable_id(e) for e in registry.enterprise_entity_ids()),
        set_document_ids=frozenset(document_ids),
        enterprise_document_ids=frozenset(registry.enterprise_document_ids()),
        set_diagram_ids=frozenset(diagram_ids),
        enterprise_diagram_ids=frozenset(registry.enterprise_diagram_ids()),
        enterprise_connection_short=frozenset(stable_conn_id(c) for c in registry.enterprise_connection_ids()),
    )


def entity_survives(entity_id: str, *, repo: "ArtifactRepository", scope: ClosureScope) -> bool:
    """Whether the enterprise holds *entity_id* once the selection is promoted.

    A diagram-only entity is satisfied through its HOST diagram: its file content
    travels with the host, so the host being in the set or enterprise closes it.
    """
    if scope.entity_satisfied(entity_id):
        return True
    record = repo.get_entity(entity_id) or repo.find_entity_by_workspace_id(entity_id)
    host = getattr(record, "host_diagram_id", None) if record is not None else None
    return bool(host) and scope.diagram_satisfied(str(host))
