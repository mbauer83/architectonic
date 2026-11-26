"""Where a candidate's picture starts: the picture its editor opens on, with the candidate as the subject.

A candidate records operations on the model, not on any one picture of it; its editor still needs a picture to
sketch on. It starts from the stored diagram the candidate's stack is drawn on, where the stack names one, and
otherwise from a view generated from the model's entities the stack reads over (`scope_drawing`), which for a
candidate that reads over nothing yet is the empty picture. What the candidate creates, changes, relates and
references beyond that start is its own record, which the editor lays over the start when it opens; nothing is
written to the model or to a diagram before the candidate is applied.

The three reads here — the start's geometry, the frontmatter an edit session's drawing is laid over, and the
record and body the editor's context is read from — are the candidate counterparts of a stored diagram's, so
one editor serves both (`rest/routers/candidate_picture.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.artifacts.repository import ArtifactRepository
from src.application.change_sets.stacking import drawn_on, stack_of
from src.application.modeling.diagram_identities import alias_by_instance
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.candidates.repository import NotStored
from src.infrastructure.candidates.scope_drawing import (
    GENERATED_VIEW_TYPE,
    generated_composition,
    generated_drawing,
    stored_drawing,
)
from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.diagram_composition import DiagramComposition, render_composition
from src.infrastructure.rendering.layout.diagram_geometry import empty_geometry
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file


@dataclass(frozen=True, slots=True)
class PictureStart:
    """Where a candidate's picture starts: a stored diagram, or the view generated from what it reads over."""

    candidate: str
    name: str
    #: The model's entities the candidate's stack reads over, by id, each once.
    scope: tuple[str, ...]
    #: The stored diagram the stack is drawn on; None where it is drawn as a generated view.
    diagram: DiagramRecord | None
    #: What the generated view draws; empty where the start is a stored diagram.
    generated: DiagramComposition

    @property
    def artifact_id(self) -> str:
        """The stored diagram's id, or none: a generated view is no artifact."""
        return self.diagram.artifact_id if self.diagram else ""


def start_of(service: CandidateService, ref: str) -> PictureStart:
    """Where *ref*'s picture starts, refused (404) where its stack names a diagram that is not stored."""
    candidate = service.store.require(ref)
    stack = stack_of(candidate, service.store.find)
    scope = tuple(dict.fromkeys(entity for layer in stack for entity in layer.scope))
    repo = ArtifactRepository(service.index)
    named = drawn_on(stack)
    diagram = repo.get_diagram(named) if named else None
    if named and diagram is None:
        raise NotStored(f"{candidate.id} is drawn on {named}, which is not stored.")
    generated = (
        DiagramComposition(diagram_type=GENERATED_VIEW_TYPE, name=candidate.name, entity_ids=[], connection_ids=[])
        if diagram else generated_composition(repo, scope, candidate.name)
    )
    return PictureStart(candidate.id, candidate.name, scope, diagram, generated)


def start_geometry(start: PictureStart, repo: Any, root: Path, ontology: DeclaresElementKinds) -> dict[str, Any]:
    """The picture *start* draws, as the canvas reads it; the empty picture where it draws nothing yet."""
    if start.diagram is not None:
        return stored_drawing(repo, start.diagram.artifact_id, root, ontology)
    drawn = generated_drawing(repo, start.scope, start.name, root, ontology)
    return drawn or empty_geometry("", start.name)


def start_frontmatter(start: PictureStart, repo: Any, root: Path) -> dict[str, Any]:
    """The statements an edit session's drawing is laid over: the stored diagram's, or the generated view's."""
    if start.diagram is not None:
        return dict(parse_diagram_file(Path(start.diagram.path)).frontmatter)
    rendered = render_composition(start.generated, repo=repo, repo_root=root)
    return {**rendered.statements(start.generated), "artifact-id": ""}


def placed_instances(frontmatter: dict[str, Any]) -> frozenset[str]:
    """The instances the start already places: an edit session's new members are placed beside them."""
    return frozenset(alias_by_instance(frontmatter))


def start_record(start: PictureStart, repo: Any, root: Path) -> tuple[DiagramRecord, str]:
    """The record and body the editor's context is read from: the stored diagram's, or the generated view's.

    Refused (`NotStored`) where the stored diagram's file cannot be read: an empty body would serve its
    context as a diagram that draws nothing.
    """
    if start.diagram is not None:
        try:
            body = Path(start.diagram.path).read_text(encoding="utf-8")
        except OSError as unreadable:
            raise NotStored(f"{start.diagram.artifact_id} is stored but cannot be read: {unreadable}") from unreadable
        return start.diagram, body
    rendered = render_composition(start.generated, repo=repo, repo_root=root)
    record = DiagramRecord(
        artifact_id="", artifact_type="diagram", name=start.name, diagram_type=start.generated.diagram_type,
        version="", status="draft", path=Path(), extra=rendered.statements(start.generated),
    )
    return record, rendered.puml
