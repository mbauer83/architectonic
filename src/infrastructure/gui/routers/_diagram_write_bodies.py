"""Request body models for the diagram/matrix GUI write endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Body(BaseModel):
    """`extra="forbid"`, and no identity field: identity is in the path, and a body that also
    accepted it would give the caller two places to say which diagram they meant."""

    model_config = ConfigDict(extra="forbid")


class DiagramPreviewBody(BaseModel):
    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    diagram_entities: dict[str, Any] | None = None


class CreateDiagramGuiBody(BaseModel):
    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    keywords: list[str] | None = None
    diagram_entities: dict[str, Any] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


class EditDiagramGuiBody(_Body):
    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    diagram_entities: dict[str, Any] | None = None
    version: str | None = None
    status: str | None = None
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


class PatchDiagramEntityMetadataBody(_Body):
    """Targeted metadata edit for one datatype classifier, or one of its attributes.

    The diagram and the classifier are path identity. ``attribute_id`` still selects between the
    classifier's own metadata and one attribute's — the attribute-scoped route that would put it in
    the path too is declared in the manifest and not yet mounted. ``patch`` carries only whitelisted
    meta fields; the write op refuses structural keys."""

    attribute_id: str | None = None
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
