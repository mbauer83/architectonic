"""Request contracts for the scratchpad write surface.

Separate from the response contracts next door because request and response genuinely differ, and
pretending otherwise is what a shared model would do: a served note carries `area`, which is derived
from where it sits and never stored, and a served note always has a `title`, while a *patch* over
one carries whichever keys are being changed and nothing else.

What they must not differ about is the vocabulary. `destination` is imported from the domain rather
than restated, because a contract that repeats an enum is a contract that can disagree with it —
which is exactly how a note carrying `destination: up2parts-autocam` came to be stored and then made
its scratchpad unreadable.

Merge-patch semantics survive the round trip through pydantic: a key the caller omitted is absent
from `model_fields_set`, a key they set to `null` is present and null, and `model_dump(by_alias=True,
exclude_unset=True)` reproduces exactly that distinction — which is the one thing the delta write
cannot afford to lose, since absent means "leave alone" and null means "clear".
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from src.domain.scratchpad import Destination, ModelRefKind
from src.infrastructure.rest.contracts.wire_shape import Closed


class ModelRefPatchWire(Closed):
    """A reference into the model, as a caller sends one.

    Deliberately not the response `ModelRefWire`, which derives from `NullsOmitted`: that base
    publishes "this schema omits nulls", a claim about *serialisation* that is untrue of a body,
    where an explicit null is a legitimate value meaning "clear this". `test_no_marked_dto_is_also_a
    _request_body` exists to catch exactly the reuse this started out as.
    """

    model_config = ConfigDict(populate_by_name=True)

    artifact_id: str = Field(alias="artifact-id")
    kind: ModelRefKind


class _Row(Closed):
    """A row a caller sends, identified by its `id`."""

    model_config = ConfigDict(populate_by_name=True)

    id: str


class _Patch(Closed):
    """A merge patch over one row.

    Closed by inheritance rather than by restating `extra="forbid"`, so a misspelled key is refused
    rather than silently doing nothing — a delta that reports success and changes nothing is the
    worst answer available, and it is the same reason `ScratchpadEdit.validate` refuses an unknown
    *collection*.
    """

    model_config = ConfigDict(populate_by_name=True)

    #: Which row to change. An id the scratchpad does not have creates it — that is how a note is
    #: added without sending the canvas.
    id: str


class NotePatchWire(_Patch):
    title: str | None = None
    body: str | None = None
    destination: Destination | None = None
    domain: str | None = None
    element_type: str | None = Field(default=None, alias="element-type")
    specialization: str | None = None
    document_type: str | None = Field(default=None, alias="document-type")
    model_ref: ModelRefPatchWire | None = Field(default=None, alias="model-ref")
    attributes: dict[str, object] | None = None
    #: Accepted and ignored. A patch is written "in the vocabulary `scratchpad_read` returns", and
    #: that vocabulary includes this — but it is derived from the layout, so a stored one would be a
    #: second answer to a question the geometry already settles.
    area: str | None = None


class AreaPatchWire(_Patch):
    label: str | None = None
    permits: dict[str, list[str]] | None = None


class GroupPatchWire(_Patch):
    label: str | None = None
    members: list[str] | None = None


class LinkPatchWire(_Patch):
    source: str | None = None
    target: str | None = None
    connection_type: str | None = Field(default=None, alias="connection-type")
    model_ref: ModelRefPatchWire | None = Field(default=None, alias="model-ref")
    #: Derived from the ontology on every read, never stored; accepted so a caller may hand back
    #: what it was given.
    verdict: dict[str, object] | None = None


class UpsertPatchWire(Closed):
    """The patches to apply, per collection.

    A model rather than `dict[str, list[dict[str, Any]]]`: the four collections are a closed set, so
    naming them here is what makes an unknown one a 422 with the field named, and what puts the
    note vocabulary — `destination` above all — into the served OpenAPI document instead of leaving
    it as an opaque object every client has to guess at.
    """

    model_config = ConfigDict(populate_by_name=True)

    areas: list[AreaPatchWire] = Field(default_factory=list)
    notes: list[NotePatchWire] = Field(default_factory=list)
    groups: list[GroupPatchWire] = Field(default_factory=list)
    links: list[LinkPatchWire] = Field(default_factory=list)

    def as_delta(self) -> dict[str, list[dict[str, object]]]:
        """The patches as the application layer's `ScratchpadEdit` takes them.

        `exclude_unset` is load-bearing, not tidiness: it is what keeps "omitted" and "null" apart,
        and those are the two halves of a merge patch.
        """
        return {
            collection: [
                patch.model_dump(by_alias=True, exclude_unset=True) for patch in patches
            ]
            for collection, patches in (
                ("areas", self.areas),
                ("notes", self.notes),
                ("groups", self.groups),
                ("links", self.links),
            )
            if patches
        }


class RemovePatchWire(Closed):
    """The ids to remove, per collection — the same closed set, for the same reason."""

    model_config = ConfigDict(populate_by_name=True)

    areas: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)

    def as_delta(self) -> dict[str, list[str]]:
        return {
            collection: ids
            for collection, ids in (
                ("areas", self.areas), ("notes", self.notes),
                ("groups", self.groups), ("links", self.links),
            )
            if ids
        }


class LayoutPatchWire(Closed):
    """Where things sit: `[x, y]` for a note, `[x, y, w, h]` for a frame, `null` to unplace.

    Links are absent because a link has no geometry of its own — it is drawn between two notes.
    """

    model_config = ConfigDict(populate_by_name=True)

    areas: dict[str, list[float] | None] = Field(default_factory=dict)
    notes: dict[str, list[float] | None] = Field(default_factory=dict)
    groups: dict[str, list[float] | None] = Field(default_factory=dict)

    def as_delta(self) -> dict[str, dict[str, list[float] | None]]:
        return {
            collection: placements
            for collection, placements in (
                ("areas", self.areas), ("notes", self.notes), ("groups", self.groups),
            )
            if placements
        }


class NoteRequestWire(_Row):
    """A note as a caller writes one. `title` is required here and optional in a *patch*: a whole
    document says what every note is, while a patch says only what changed."""

    title: str
    body: str = ""
    destination: Destination = "undecided"
    domain: str | None = None
    element_type: str | None = Field(default=None, alias="element-type")
    specialization: str | None = None
    document_type: str | None = Field(default=None, alias="document-type")
    model_ref: ModelRefPatchWire | None = Field(default=None, alias="model-ref")
    attributes: dict[str, object] = Field(default_factory=dict)
    #: Derived from geometry and served on every read, so a caller handing back what it was given
    #: sends it. Accepted and ignored — the layout is the one answer to where a note sits.
    area: str | None = None


class AreaRequestWire(_Row):
    label: str = ""
    permits: dict[str, list[str]] = Field(default_factory=dict)
    #: The served spelling of the same thing. A frame declares domains; the element and document
    #: types are derived from the ontology, so they are read back and dropped rather than stored.
    permitted_domains: list[str] = Field(default_factory=list, alias="permitted-domains")
    permitted_element_types: list[str] = Field(default_factory=list, alias="permitted-element-types")
    permitted_document_types: list[str] = Field(default_factory=list, alias="permitted-document-types")


class GroupRequestWire(_Row):
    label: str = ""
    members: list[str] = Field(default_factory=list)


class LinkRequestWire(_Row):
    source: str
    target: str
    connection_type: str | None = Field(default=None, alias="connection-type")
    model_ref: ModelRefPatchWire | None = Field(default=None, alias="model-ref")
    #: Recomputed from the ontology on every read and never stored; accepted so a caller may hand
    #: back the document it was given.
    verdict: dict[str, object] | None = None


class ScratchpadDocumentWire(Closed):
    """A whole scratchpad as a caller sends it, for `PUT` and for `scratchpad_replace`.

    Not `ScratchpadResponse`. The two describe the same document from opposite directions and differ
    where that matters: a served note always carries `area` and a served link always carries a
    `verdict`, both derived, and neither is something a writer must supply. Sharing one model would
    have forced a caller to send back values it does not own.

    What it *does* accept is everything a read returns, because the documented loop is "read it, edit
    it, hand it back". The derived keys are declared so they are accepted and dropped, rather than
    rejected by a closed model or, worse, quietly stored as a second answer to a question the
    geometry and the ontology already settle.
    """

    model_config = ConfigDict(populate_by_name=True)

    #: Ignored in favour of the address in the URL: the two disagreeing is a client bug, not a
    #: rename, and `from_document` already resolves it that way.
    artifact_id: str | None = Field(default=None, alias="artifact-id")
    artifact_type: str | None = Field(default=None, alias="artifact-type")
    name: str = ""
    description: str = ""
    #: The concurrency token travels beside the document, not inside it; read back and ignored here.
    version: str | None = None
    status: str | None = None
    #: Which collection it sits in. `PUT` takes this as its own field, so a document carrying one is
    #: echoing what it read.
    group: str | None = None
    meta_ontology: str | None = Field(default=None, alias="meta-ontology")
    attributes: dict[str, object] = Field(default_factory=dict)
    areas: list[AreaRequestWire] = Field(default_factory=list)
    notes: list[NoteRequestWire] = Field(default_factory=list)
    links: list[LinkRequestWire] = Field(default_factory=list)
    groups: list[GroupRequestWire] = Field(default_factory=list)
    layout: LayoutPatchWire = Field(default_factory=LayoutPatchWire)

    def as_document(self) -> dict[str, object]:
        """The document vocabulary `from_document` reads — kebab-case, derived keys dropped.

        `exclude_none` rather than `exclude_unset`: unlike a patch, a whole document has no "leave
        this alone", so a null and an omission mean the same thing and both mean absent.
        """
        return self.model_dump(by_alias=True, exclude_none=True)
