"""Request body models for the diagram/matrix GUI write endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.infrastructure.artifact_home_wire import FiledOnCreate
from src.infrastructure.diagram_composition import DiagramComposition, _Body


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
