"""Response contracts for the scratchpad surface.

The wire shape is the aggregate's shape, in the repository's kebab-case convention — the same
vocabulary the YAML file uses, so a person reading a response and a person reading the file are
reading one thing. A DTO that renamed the aggregate's fields would be a third vocabulary to keep in
step with the other two.

`layout` is carried as its own block rather than folded into each note, for the reason the file
does the same: a save that only moved things must be legible as such.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class ModelRefWire(NullsOmitted):
    """A one-way reference into the model. `kind` records how the note came by it."""

    artifact_id: str = Field(alias="artifact-id")
    kind: Literal["realized", "bound"]


class NoteWire(NullsOmitted):
    """A note. Only `id` and `title` are ever required — that is the feature."""

    id: str
    title: str
    body: str = ""
    destination: Literal["undecided", "element", "document", "none"] = "undecided"
    element_type: str | None = Field(default=None, alias="element-type")
    specialization: str | None = None
    document_type: str | None = Field(default=None, alias="document-type")
    model_ref: ModelRefWire | None = Field(default=None, alias="model-ref")
    attributes: dict[str, object] = Field(default_factory=dict)
    #: Derived from geometry, never stored — served because every client would otherwise
    #: recompute point-in-rect over the layout block, and derive it slightly differently.
    area: str


class LinkWire(NullsOmitted):
    id: str
    source: str
    target: str
    connection_type: str | None = Field(default=None, alias="connection-type")
    model_ref: ModelRefWire | None = Field(default=None, alias="model-ref")


class AreaWire(NullsOmitted):
    id: str
    label: str
    permitted_element_types: list[str] = Field(default_factory=list, alias="permitted-element-types")
    permitted_document_types: list[str] = Field(default_factory=list, alias="permitted-document-types")


class GroupWire(NullsOmitted):
    id: str
    label: str
    members: list[str] = Field(default_factory=list)


class LayoutWire(NullsOmitted):
    """Geometry, apart from content. Rects are `[x, y, w, h]`, points `[x, y]`."""

    areas: dict[str, list[float]] = Field(default_factory=dict)
    notes: dict[str, list[float]] = Field(default_factory=dict)
    groups: dict[str, list[float]] = Field(default_factory=dict)


class ScratchpadSummaryWire(NullsOmitted):
    """What a list returns: enough to choose one, never the notes."""

    artifact_id: str = Field(alias="artifact-id")
    name: str
    description: str = ""
    status: str
    version: str
    group: str
    meta_ontology: str = Field(alias="meta-ontology")
    note_count: int = Field(alias="note-count")


class ScratchpadListResponse(NullsOmitted):
    scratchpads: list[ScratchpadSummaryWire]


class ScratchpadResponse(NullsOmitted):
    """The whole aggregate. There is no partial read, because there is no partial write."""

    artifact_id: str = Field(alias="artifact-id")
    artifact_type: Literal["scratchpad"] = Field(default="scratchpad", alias="artifact-type")
    name: str
    description: str = ""
    version: str
    status: str
    group: str
    meta_ontology: str = Field(alias="meta-ontology")
    attributes: dict[str, object] = Field(default_factory=dict)
    areas: list[AreaWire] = Field(default_factory=list)
    notes: list[NoteWire] = Field(default_factory=list)
    links: list[LinkWire] = Field(default_factory=list)
    groups: list[GroupWire] = Field(default_factory=list)
    layout: LayoutWire = Field(default_factory=LayoutWire)
