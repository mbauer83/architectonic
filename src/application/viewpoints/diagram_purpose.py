"""Who a diagram is for and what it answers, once the viewpoint it applies has had its say.

A diagram's own purpose line wins, list by list; a list it does not state is its viewpoint's
(`PurposeLines.over`). Asked by the diagram read, the diagram list's stakeholder filter and an element's
page ("views that address this"), so all three agree about which diagram addresses whom.

A read never fails over a stored value: a purpose line that cannot be read counts as stating nothing,
and a viewpoint application that cannot be read as applying none. The verifier reports both (E185, and
the viewpoint rules), which is where a reader is told.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.domain.purpose_lines import MalformedPurposeLine, Prose, PurposeLines, read_purpose_lines
from src.domain.viewpoints.viewpoint_application_parsing import parse_viewpoint_application
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition


@dataclass(frozen=True)
class DiagramPurpose:
    """The lines a diagram shows, and the viewpoint any of them came from."""

    lines: PurposeLines
    #: The slug of the viewpoint supplying at least one list; None where every shown list is the diagram's own.
    inherited_from: str | None = None


def _own_lines(frontmatter: Mapping[str, object]) -> PurposeLines:
    try:
        return read_purpose_lines(frontmatter)
    except MalformedPurposeLine:
        return PurposeLines()


def _applied_viewpoint(frontmatter: Mapping[str, object], viewpoints: ViewpointCatalog) -> ViewpointDefinition | None:
    try:
        application = parse_viewpoint_application(frontmatter.get("viewpoint"), target_kind="diagram", target_id="")
    except ValueError:
        return None
    return viewpoints.get(application.viewpoint_slug) if application is not None else None


def diagram_purpose(frontmatter: Mapping[str, object], viewpoints: ViewpointCatalog) -> DiagramPurpose:
    """The purpose line *frontmatter*'s diagram shows: its own, over its viewpoint's."""
    own = _own_lines(frontmatter)
    definition = _applied_viewpoint(frontmatter, viewpoints)
    if definition is None:
        return DiagramPurpose(own)
    shown = own.over(definition.purpose_lines)
    return DiagramPurpose(shown, inherited_from=definition.slug if shown != own else None)


def addresses_stakeholder(purpose: DiagramPurpose, stakeholder: str) -> bool:
    """Whether a diagram is for *stakeholder*: an element's id, or the words a prose entry states."""
    wanted = stakeholder.strip().casefold()
    return PurposeLines(stakeholders=purpose.lines.stakeholders).names(stakeholder) or any(
        isinstance(entry, Prose) and entry.text.casefold() == wanted for entry in purpose.lines.stakeholders
    )


def diagrams_addressing(
    artifact_id: str, diagrams: Iterable[DiagramRecord], viewpoints: ViewpointCatalog
) -> list[DiagramRecord]:
    """The diagrams whose shown purpose line refers to *artifact_id*, as a stakeholder or a concern."""
    return [
        diagram for diagram in diagrams
        if diagram_purpose(diagram.extra, viewpoints).lines.names(artifact_id)
    ]
