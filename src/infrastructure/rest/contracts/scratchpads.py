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
    #: The first classification level. Chosen before a type, and **derived from the type** once one
    #: is — the type is the more specific decision, and two places to read it from is two answers
    #: waiting to disagree.
    domain: str | None = None
    element_type: str | None = Field(default=None, alias="element-type")
    specialization: str | None = None
    document_type: str | None = Field(default=None, alias="document-type")
    model_ref: ModelRefWire | None = Field(default=None, alias="model-ref")
    attributes: dict[str, object] = Field(default_factory=dict)
    #: Derived from geometry, never stored — served because every client would otherwise
    #: recompute point-in-rect over the layout block, and derive it slightly differently.
    area: str


class LinkVerdictWire(NullsOmitted):
    """What the meta-ontology says about a drawn link.

    Served with the link rather than behind its own endpoint: the two-tier split is a property of
    the ontology's declared classification levels, and deciding it a second time in a client would
    put it in two places. `blocks` distinguishes a refusal, which stops a lift, from a narrowing,
    which warns.
    """

    kind: Literal["unverified", "reference", "permitted", "narrowed", "refused"]
    code: str = ""
    message: str = ""
    #: Connection types the ontology permits for this pair — offered as "did you mean one of these".
    alternatives: list[str] = Field(default_factory=list)
    #: Leads the remedies: dragging an ordered triple the wrong way is the commonest slip there is.
    reverse_permitted: bool | None = Field(default=None, alias="reverse-permitted")
    narrowed_by: str | None = Field(default=None, alias="narrowed-by")
    blocks: bool | None = None


class LinkWire(NullsOmitted):
    id: str
    source: str
    target: str
    connection_type: str | None = Field(default=None, alias="connection-type")
    model_ref: ModelRefWire | None = Field(default=None, alias="model-ref")
    #: Present on a read; absent from the stored file, because a verdict is derived from an
    #: ontology that may change under a stored scratchpad.
    verdict: LinkVerdictWire | None = None


class AreaWire(NullsOmitted):
    """A labelled frame, and what it narrows to.

    `permitted-element-types` is **derived**: a frame declares the *domains* it holds — motivation
    and strategy for Vision & strategy, none at all for the three that reach across the model — and
    the types follow from whatever the ontology currently declares. Served rather than resolved by
    each client, for the same reason a note's `area` is.
    """

    id: str
    label: str
    permitted_domains: list[str] = Field(default_factory=list, alias="permitted-domains")
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


class LiftTargetWire(NullsOmitted):
    """One project a lift lands in — one per frame, chosen at lift time rather than stored."""

    group: str = ""
    meta_ontology: str = Field(default="", alias="meta-ontology")
    exists: bool = False


class LiftItemWire(NullsOmitted):
    """One selected note or link, and what the lift would do with it."""

    kind: Literal["element", "document", "connection", "reference"]
    id: str
    outcome: Literal["create", "skip", "refuse"]
    label: str
    artifact_type: str = Field(default="", alias="artifact-type")
    #: What a skipped note already is, so the report names it rather than saying "already done".
    artifact_id: str = Field(default="", alias="artifact-id")
    code: str = ""
    reason: str = ""
    #: A narrowing (W128/W129). Reported and passed, because the relation exists.
    warning: str = ""
    #: The project this lands in — the target of the frame the note sits in.
    target: str = ""


class OutsideSelectionWire(NullsOmitted):
    """A link with one end in the selection and one end out — a decision, not an error."""

    link_id: str = Field(alias="link-id")
    note_id: str = Field(alias="note-id")
    note_title: str = Field(alias="note-title")


class ScratchpadLiftResponse(NullsOmitted):
    """The preflight, and what the execution did if it ran.

    One shape for both, because they are one operation: a plan that could only be executed by a
    second call would be a plan made against a scratchpad that may have moved on. `committed` is
    what distinguishes an answer that wrote from one that only reported.
    """

    targets: list[LiftTargetWire] = Field(default_factory=list)
    items: list[LiftItemWire] = Field(default_factory=list)
    outside_selection: list[OutsideSelectionWire] = Field(
        default_factory=list, alias="outside-selection"
    )
    #: Set when the lift itself is refused rather than any one item — an empty selection, an unknown
    #: note, or a target whose meta-ontology is not this scratchpad's. Nothing is planned when set.
    refusal: str = ""
    #: Whether anything stops the lift. A refusal anywhere blocks all of it: the write is one
    #: transaction, and half a lift is a state nobody asked for.
    blocks: bool = False
    dry_run: bool = Field(default=True, alias="dry-run")
    committed: bool = False
    #: note id / link id → the artifact the write allocated for it.
    realized: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    operation_id: str = Field(default="", alias="operation-id")
