"""Request body models for the diagram/matrix GUI write endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


class EditDiagramGuiBody(BaseModel):
    artifact_id: str
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


class PatchDiagramEntityMetadataBody(BaseModel):
    """Targeted metadata edit for one datatype classifier (attribute_id omitted) or one of its
    attributes (attribute_id set). ``patch`` carries only whitelisted meta fields; the write op
    refuses structural keys."""

    artifact_id: str
    classifier_id: str
    attribute_id: str | None = None
    patch: dict[str, Any]
    dry_run: bool = True


class DeleteDiagramBody(BaseModel):
    artifact_id: str
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


class EditMatrixBody(BaseModel):
    artifact_id: str
    name: str
    entity_ids: list[str]
    conn_type_configs: list[dict[str, object]]
    combined: bool = False
    version: str | None = None
    status: str | None = None
    dry_run: bool = True
    from_entity_ids: list[str] | None = None
    to_entity_ids: list[str] | None = None


class SyncDiagramToModelBody(BaseModel):
    artifact_id: str
    dry_run: bool = True
