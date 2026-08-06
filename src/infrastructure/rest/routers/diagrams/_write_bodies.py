"""Request body models for the diagram/matrix GUI write endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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


class DiagramPreviewBody(DiagramComposition):
    """A composition, rendered but not written. It adds nothing, which is the point."""


class CreateDiagramGuiBody(DiagramComposition):
    keywords: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


class EditDiagramGuiBody(DiagramComposition, _Body):
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
