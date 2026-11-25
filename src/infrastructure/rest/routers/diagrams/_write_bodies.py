"""Request body models for the diagram/matrix GUI write endpoints."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from src.domain.diagrams.grouping_intents import Nest, Unnest, regrouped
from src.domain.diagrams.layout.arrange_intents import read_intents
from src.infrastructure.rest.contracts.artifact_home import FiledOnCreate, Rehomeable
from src.infrastructure.write.artifact_write.canvas_commands import CanvasCommand


class _Body(BaseModel):
    """`extra="forbid"`, and no identity field: identity is in the path, and a body that also
    accepted it would give the caller two places to say which diagram they meant."""

    model_config = ConfigDict(extra="forbid")


class DiagramComposition(BaseModel):
    """What a diagram draws, declared once for every surface that renders one.

    Preview, create and replace all render the *same* picture, so the fields describing it belong in
    one place. They were declared three times, and the cost showed: `authored_groupings` reached
    create and replace while preview kept its own copy of the field list, so a diagram's custom boxes
    appeared in the written diagram and never in the preview of it. A preview missing a field is a
    picture of a diagram the write will not make, which is worse than no preview at all.

    Fields the *operation* decides — a version, a status, whether it is a dry run — stay on the body
    that decides them. This carries only what ends up in the picture.
    """

    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    diagram_entities: dict[str, Any] | None = None
    authored_groupings: list[dict[str, Any]] | None = None
    #: Nest and unnest intents (as the arrange route takes them), applied to `authored_groupings` as the
    #: body is read: what an editor kept of moving elements into and out of the diagram's own boxes,
    #: compiled by the one grouping compiler (`grouping_intents.regrouped`). Applied here, every surface
    #: that renders or writes a composition reads the same groupings, and none can forget the intents.
    grouping_intents: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _regrouped(self) -> Self:
        """The groupings after the intents, in order; refuses one that cannot apply, saying why.

        Only moving instances between groupings is taken here: creating or deleting a grouping, and any
        intent that states geometry, is the arrange route's.
        """
        if not self.grouping_intents:
            return self
        groupings: list[object] = list(self.authored_groupings or [])
        for intent in read_intents(self.grouping_intents):
            if not isinstance(intent, Nest | Unnest):
                kind = type(intent).__name__
                raise ValueError(f"A composition takes nest and unnest intents only; {kind} is the arrange route's.")
            # No grouping is created here, so no grouping id is seeded from the diagram's.
            groupings = [*regrouped(intent, groupings, diagram_id="").groupings]
        self.authored_groupings = [dict(grouping) for grouping in groupings if isinstance(grouping, dict)]
        self.grouping_intents = None
        return self


class DiagramPreviewBody(DiagramComposition):
    """A composition, rendered but not written. It adds nothing, which is the point."""


class CreateDiagramGuiBody(DiagramComposition, FiledOnCreate):
    #: The whole layout block to store with the new diagram. Read and refused by the layout's own
    #: reader, so a malformed block is answered with its sentence rather than a schema error.
    layout: dict[str, Any] | None = None
    keywords: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


class EditDiagramGuiBody(DiagramComposition, _Body, Rehomeable):
    commands: list[CanvasCommand] = []
    #: The whole layout block to store. Absent keeps the diagram's own; an empty object removes it
    #: and returns the diagram to PlantUML's arrangement with nothing else changed.
    layout: dict[str, Any] | None = None
    #: Instead of a whole block: entries of the layout patch (as `PATCH …/layout` takes them), applied to
    #: the stored layout in the same write that changes the membership, which then drops whatever names
    #: what the diagram no longer holds (D12). So the stored layout always matches the body written.
    layout_patch: dict[str, dict[str, Any]] | None = None
    version: str | None = None
    status: str | None = None
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


class PatchDiagramEntityMetadataBody(_Body):
    """Targeted metadata edit for one datatype classifier, or for one of its attributes.

    Every identity is in the path — the diagram, the classifier, and for the attribute-scoped route
    the attribute. ``attribute_id`` used to live *here*, where it selected between two different
    addressed resources: present, the request edited an attribute; absent, the classifier. One body
    field deciding which of two things is being written is the shape this redesign exists to remove,
    and being closed (``extra="forbid"``) the model now rejects it outright rather than ignoring it.

    ``patch`` carries only whitelisted meta fields; the write op refuses structural keys.
    """

    patch: dict[str, Any]
    dry_run: bool = True


class MatrixPreviewBody(BaseModel):
    entity_ids: list[str]
    conn_type_configs: list[dict[str, object]]
    combined: bool = False
    from_entity_ids: list[str] | None = None
    to_entity_ids: list[str] | None = None


class CreateMatrixBody(BaseModel):
    name: str
    entity_ids: list[str]
    conn_type_configs: list[dict[str, object]]
    combined: bool = False
    keywords: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    dry_run: bool = True
    from_entity_ids: list[str] | None = None
    to_entity_ids: list[str] | None = None


class EditMatrixBody(_Body):
    name: str
    entity_ids: list[str]
    conn_type_configs: list[dict[str, object]]
    combined: bool = False
    version: str | None = None
    status: str | None = None
    dry_run: bool = True
    from_entity_ids: list[str] | None = None
    to_entity_ids: list[str] | None = None


class SyncDiagramToModelBody(_Body):
    dry_run: bool = True
