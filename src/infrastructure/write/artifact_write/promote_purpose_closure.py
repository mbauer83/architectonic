"""Plan-time closure for purpose lines: a promoted diagram's or viewpoint's stakeholder and concern references
must name elements the enterprise repository holds after the promotion.

A reference to an element that stays engagement-side would dangle enterprise-side — the enterprise
verifier's E186 for a diagram, and for a viewpoint a definition that names nothing. Whether a reference
resolves is `PurposeLineResolution`'s to decide, the check both verifiers use; this module only hands it
the post-promotion view — an engagement record counts as held when the enterprise holds it already or the
same promotion carries it along — and reports each dangling reference as a missing dependency, so the
operator can add the element to the set. A reference of an unsuitable type is the engagement verifier's
finding (E187) and is not repeated here; prose names nothing and is never looked at.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.verification.purpose_line_references import Missing, PurposeLineResolution
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.purpose_lines import MalformedPurposeLine, PurposeLines, read_purpose_lines
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.write.artifact_write.promote_closure_scope import ClosureScope, entity_survives
from src.infrastructure.write.artifact_write.promote_reference_closure import MissingDependency

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactRegistry
    from src.domain.ontology_representation.purpose_line_elements import PurposeLineTypes
    from src.domain.viewpoints.viewpoints import ViewpointDefinition


@dataclass(frozen=True)
class _PostPromotionEntities:
    """The elements the enterprise repository holds once this promotion is done."""

    repo: "ArtifactRepository"
    scope: ClosureScope

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        record = self.repo.get_entity(artifact_id)
        return record if record is not None and entity_survives(artifact_id, repo=self.repo, scope=self.scope) else None


def _diagram_lines(diagram_id: str, registry: "ArtifactRegistry") -> PurposeLines:
    path = registry.find_file_by_id(diagram_id)
    if path is None:
        return PurposeLines()
    try:
        return read_purpose_lines(parse_frontmatter(path.read_text(encoding="utf-8")))
    except MalformedPurposeLine:
        return PurposeLines()  # unreadable — the engagement verifier's E185, not a closure fact


def purpose_line_closure(
    *,
    diagram_ids: Sequence[str],
    viewpoints: Sequence["ViewpointDefinition"],
    scope: ClosureScope,
    repo: "ArtifactRepository",
    registry: "ArtifactRegistry",
    admitted: "PurposeLineTypes",
) -> list[MissingDependency]:
    """Every purpose-line reference of the promoted diagrams and viewpoints that would dangle enterprise-side."""
    resolution = PurposeLineResolution(_PostPromotionEntities(repo, scope), admitted)
    holders = [(diagram_id, _diagram_lines(diagram_id, registry)) for diagram_id in diagram_ids] + [
        (f"viewpoint '{definition.slug}'", definition.purpose_lines) for definition in viewpoints
    ]
    return [
        MissingDependency(
            artifact_id=unresolved.placed.reference.artifact_id,
            name=_name_of(unresolved.placed.reference.artifact_id, repo),
            record_type="entity",
            required_by=holder,
            kind="purpose_line_reference",
        )
        for holder, lines in holders
        for unresolved in resolution.unresolved(lines)
        if isinstance(unresolved.fault, Missing)
    ]


def _name_of(artifact_id: str, repo: "ArtifactRepository") -> str:
    record = repo.get_entity(artifact_id)
    return record.name if record is not None else artifact_id
