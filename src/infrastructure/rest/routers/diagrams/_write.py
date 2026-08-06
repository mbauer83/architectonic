"""Diagram write (POST) endpoints for the diagram GUI router."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.application.derivation.preview import project_view_for_preview
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.diagrams.diagram_selection import DiagramSelectionError
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rendering.diagram_selection import resolve_diagram_selection
from src.infrastructure.rest.contracts.diagrams import DiagramPreviewResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._failures import rejected_input
from src.infrastructure.rest.routers._openapi import (
    TAG_DIAGRAMS,
    WRITE_RESPONSES,
    WriteResultResponse,
)
from src.infrastructure.rest.routers.diagrams._write_bodies import (
    CreateDiagramGuiBody,
    DiagramComposition,
    DiagramPreviewBody,
    EditDiagramGuiBody,
    PatchDiagramEntityMetadataBody,
    SyncDiagramToModelBody,
)
from src.infrastructure.rest.routers.diagrams._write_responses import (
    CREATE_RESPONSES,
    DELETE_RESPONSES,
    DETAIL_RESPONSES,
    SyncDiagramToModelResponse,
    created,
)

router = APIRouter(responses=WRITE_RESPONSES)

def _split_diagram_entities(
    diagram_entities: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Separate the transport-only `_connections` key from entity data."""
    if diagram_entities is None:
        return None, None
    conns = diagram_entities.get("_connections")
    if conns is None:
        return diagram_entities, None
    clean = {k: v for k, v in diagram_entities.items() if k != "_connections"}
    return clean or None, conns if isinstance(conns, list) else None


def _extract_conn_bindings(
    connections: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Strip `backing_conn_id` from connections; return (clean, binding_dicts)."""
    if not connections:
        return connections, []
    bindings: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            clean.append(conn)
            continue
        backing_id = conn.get("backing_conn_id")
        conn_id = conn.get("id")
        if backing_id and conn_id:
            bindings.append({
                "id": f"bind-conn-{conn_id}",
                "subject": {"kind": "connection", "id": conn_id},
                "correspondence_kind": "represents",
                "target": {"connection_id": backing_id},
            })
        clean.append({k: v for k, v in conn.items() if k != "backing_conn_id"})
    return clean or None, bindings


@dataclass(frozen=True)
class _RenderedComposition:
    """One composition, resolved and rendered — the same way for every surface that shows it."""

    entities: list[Any]
    connections: list[Any]
    entity_ids_used: list[str]
    connection_ids_used: list[str]
    diagram_entities: dict[str, Any] | None
    diagram_connections: list[dict[str, Any]] | None
    conn_bindings: list[dict[str, Any]]
    puml: str


def _render_composition(body: DiagramComposition, *, repo: Any, repo_root: Path) -> _RenderedComposition:
    """Resolve a composition and render it, once, for preview and for both writes.

    The three surfaces used to assemble this themselves, and drifted twice over: preview never passed
    `authored_groupings`, so custom boxes were invisible until the write; and preview rendered with
    connection *bindings* still attached while the writes stripped them first, so the two were not
    rendering the same input either. A preview is only worth having if it is the write's own picture.
    """
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body  # noqa: PLC0415

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo, body.entity_ids, body.connection_ids
    )
    de, dc = _split_diagram_entities(body.diagram_entities)
    dc, conn_bindings = _extract_conn_bindings(dc)
    puml = generate_archimate_puml_body(
        body.name,
        entities,
        connections,
        diagram_type=body.diagram_type,
        repo_root=repo_root,
        diagram_entities=de,
        diagram_connections=dc,
        authored_groupings=body.authored_groupings,
    )
    return _RenderedComposition(
        entities=entities, connections=connections,
        entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
        diagram_entities=de, diagram_connections=dc, conn_bindings=conn_bindings, puml=puml,
    )


@router.post("/api/diagrams/preview", tags=[TAG_DIAGRAMS], summary="Preview a diagram write (dry-run)",
    response_model=DiagramPreviewResponse, responses=WRITE_RESPONSES)
def preview_diagram(body: DiagramPreviewBody, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)) -> dict[str, Any]:  # noqa: E501
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.infrastructure.rendering.diagram_builder import render_puml_preview

    repo = s.get_repo()
    query = shared_artifact_index([repo_root])

    # A selection this diagram type cannot draw is a rejected input, not a broken server: a C4
    # scope naming an entity the repository does not hold used to reach the unhandled-exception
    # handler and answer 500, whose body deliberately carries none of the exception text — so the
    # caller was told the server was broken and the only diagnostic stayed in the log. Config and
    # renderer faults still raise plain ValueError and still answer 500, which is honest for them.
    try:
        composed = _render_composition(body, repo=repo, repo_root=repo_root)
    except DiagramSelectionError as exc:
        raise rejected_input(str(exc), field="diagram_entities") from exc
    puml, de = composed.puml, composed.diagram_entities
    image, warnings = render_puml_preview(puml, repo_root, body.diagram_type)

    items = project_view_for_preview(catalogs.diagram_types.get_diagram_type(body.diagram_type), body.diagram_type, de or {}, query)  # noqa: E501
    derived_entities = None if items is None else [{"id": i.entity_id, "name": i.name, "item_type": i.display_class, "role": i.role, "excluded": i.excluded} for i in items]  # noqa: E501
    return {"puml": puml, "image": image, "warnings": warnings, "derived_entities": derived_entities}


@router.post("/api/diagrams", tags=[TAG_DIAGRAMS], summary="Create a diagram",
    response_model=WriteResultResponse, responses=CREATE_RESPONSES,
    status_code=status.HTTP_201_CREATED)
def create_diagram_gui(body: CreateDiagramGuiBody, response: Response,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.application.identifier_allocator import get_default_allocator
    from src.application.modeling.artifact_write import prefix_for_diagram_type
    from src.infrastructure.write.artifact_write.diagram import create_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps(catalogs)
    composed = _render_composition(body, repo=repo, repo_root=repo_root)
    puml, de, dc = composed.puml, composed.diagram_entities, composed.diagram_connections
    conn_bindings = composed.conn_bindings
    entity_ids_used, connection_ids_used = composed.entity_ids_used, composed.connection_ids_used
    try:
        result = s.authorized_write(
            "diagrams_create_diagram", 
            create_diagram,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            diagram_type=body.diagram_type,
            name=body.name,
            puml=puml,
            artifact_id=get_default_allocator().allocate(
                prefix=prefix_for_diagram_type(body.diagram_type), name_hint=body.name
            ),
            keywords=body.keywords,
            diagram_entities=de,
            diagram_connections=dc,
            entity_ids_used=entity_ids_used,
            connection_ids_used=connection_ids_used,
            authored_groupings=body.authored_groupings,
            version=body.version,
            status=body.status,
            last_updated=None,
            tlp=body.tlp,
            connection_inference="none",
            bindings=conn_bindings or None,
            viewpoint=body.viewpoint,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    created(result, response, f"/api/diagrams/{result.artifact_id}")
    return s.write_result_to_dict(result)


@router.put("/api/diagrams/{artifact_id}", tags=[TAG_DIAGRAMS], summary="Replace a diagram",
    response_model=WriteResultResponse, responses=DETAIL_RESPONSES)
def edit_diagram_gui(artifact_id: str, body: EditDiagramGuiBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps(catalogs)
    composed = _render_composition(body, repo=repo, repo_root=repo_root)
    puml, de, dc = composed.puml, composed.diagram_entities, composed.diagram_connections
    conn_bindings = composed.conn_bindings
    entity_ids_used, connection_ids_used = composed.entity_ids_used, composed.connection_ids_used
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    try:
        result = s.authorized_write(
            "diagrams_replace_diagram", 
            edit_diagram,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            puml=puml,
            name=body.name,
            keywords=...,
            diagram_entities=de,
            diagram_connections=dc,
            entity_ids_used=entity_ids_used,
            connection_ids_used=connection_ids_used,
            authored_groupings=body.authored_groupings,
            version=body.version,
            status=body.status,
            tlp=body.tlp,
            bindings=conn_bindings or None,
            viewpoint=body.viewpoint,
            dry_run=body.dry_run,
            committed_repo=committed_repository(repo),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


def _patch_diagram_metadata(
    *, operation_id: str, artifact_id: str, classifier_id: str, attribute_id: str | None,
    body: PatchDiagramEntityMetadataBody,
    catalogs: RuntimeCatalogs,
) -> dict[str, Any]:
    """The one write behind both metadata routes, differing only in what the path addressed.

    Shared rather than duplicated: the two routes are the same mutation on two scopes, and the scope
    is now decided by the address instead of by a body field. Each passes its own operation id, so
    authorization stays per-operation.
    """
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_entity_metadata_patch import (  # noqa: PLC0415
        patch_diagram_entity_metadata,
    )

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            operation_id,
            patch_diagram_entity_metadata,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            classifier_id=classifier_id,
            attribute_id=attribute_id,
            patch=body.patch,
            dry_run=body.dry_run,
            committed_repo=committed_repository(repo),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.patch("/api/diagrams/{artifact_id}/entities/{classifier_id}/metadata", tags=[TAG_DIAGRAMS],
    summary="Patch a diagram-entity's metadata", response_model=WriteResultResponse)
def patch_diagram_entity_metadata_gui(
    artifact_id: str, classifier_id: str, body: PatchDiagramEntityMetadataBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    return _patch_diagram_metadata(
        operation_id="diagrams_update_diagram_classifier_metadata",
        artifact_id=artifact_id, classifier_id=classifier_id, attribute_id=None, body=body,
        catalogs=catalogs,
    )


@router.patch(
    "/api/diagrams/{artifact_id}/entities/{classifier_id}/attributes/{attribute_id}/metadata",
    tags=[TAG_DIAGRAMS], summary="Patch one attribute's metadata on a diagram-entity",
    response_model=WriteResultResponse)
def patch_diagram_attribute_metadata_gui(
    artifact_id: str, classifier_id: str, attribute_id: str,
    body: PatchDiagramEntityMetadataBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """The attribute's own address, split out of the classifier route.

    One optional body field used to choose between editing the classifier and editing one of its
    attributes — two different resources behind one address, which no cache directive, authorization
    row or reader could tell apart. They are two addresses now, and the classifier body no longer
    accepts the field.
    """
    return _patch_diagram_metadata(
        operation_id="diagrams_update_diagram_attribute_metadata",
        artifact_id=artifact_id, classifier_id=classifier_id, attribute_id=attribute_id, body=body,
        catalogs=catalogs,
    )


@router.post("/api/diagrams/{artifact_id}/sync", tags=[TAG_DIAGRAMS], summary="Sync a diagram to the model",
    response_model=SyncDiagramToModelResponse, responses=WRITE_RESPONSES)
def sync_diagram_to_model_gui(artifact_id: str, body: SyncDiagramToModelBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.diagram_sync import refresh_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "diagrams_sync_diagram_to_model", 
            refresh_diagram,
            repo_root=repo_root,
            store=repo,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    d = s.write_result_to_dict(result)
    # All three of the sync result's own fields, `deleted_diagram` included: it was left out, so the one
    # guarantee this operation makes about the file it touched was absent from the body that reports on it.
    d.update(
        removed_entity_ids=result.removed_entity_ids,
        removed_connection_ids=result.removed_connection_ids,
        deleted_diagram=result.deleted_diagram,
    )
    return d


@router.delete("/api/diagrams/{artifact_id}", tags=[TAG_DIAGRAMS], summary="Remove a diagram",
    response_model=None, responses=DELETE_RESPONSES, status_code=status.HTTP_204_NO_CONTENT)
def delete_diagram_gui(
    artifact_id: str, response: Response, dry_run: bool = True,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any] | None:
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_delete import delete_diagram

    repo = s.get_repo()
    repo_root, _registry, _verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "diagrams_delete_diagram", 
            delete_diagram,
            repo_root=repo_root,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            dry_run=dry_run,
            verifier=_verifier,
            committed_repo=committed_repository(repo),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    # A committed removal has nothing to report; a dry run has its plan, which needs a status that
    # permits a body.
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None
