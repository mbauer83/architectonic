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
