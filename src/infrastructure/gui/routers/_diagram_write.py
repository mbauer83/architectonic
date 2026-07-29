"""Diagram write (POST) endpoints for the diagram GUI router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.derivation.preview import project_view_for_preview
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._diagram_selection import resolve_diagram_selection
from src.infrastructure.gui.routers._diagram_write_bodies import (
    CreateDiagramGuiBody,
    CreateMatrixBody,
    DeleteDiagramBody,
    DiagramPreviewBody,
    EditDiagramGuiBody,
    EditMatrixBody,
    MatrixPreviewBody,
    PatchDiagramEntityMetadataBody,
    SyncDiagramToModelBody,
)
from src.infrastructure.gui.routers._matrix_markdown import build_matrix_markdown
from src.infrastructure.gui.routers._openapi import TAG_DIAGRAMS, WRITE_RESPONSES, OpenMapResponse

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


@router.post("/api/diagram/preview", tags=[TAG_DIAGRAMS], summary="Preview a diagram write (dry-run)",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def preview_diagram(body: DiagramPreviewBody, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)) -> dict[str, Any]:  # noqa: E501
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body, render_puml_preview

    repo = s.get_repo()
    entities, connections, _, _ = resolve_diagram_selection(repo, body.entity_ids, body.connection_ids)
    de, dc = _split_diagram_entities(body.diagram_entities)

    query = shared_artifact_index([repo_root])

    puml = generate_archimate_puml_body(
        body.name,
        entities,
        connections,
        diagram_type=body.diagram_type,
        repo_root=repo_root,
        diagram_entities=de,
        diagram_connections=dc,
    )
    image, warnings = render_puml_preview(puml, repo_root, body.diagram_type)

    items = project_view_for_preview(catalogs.diagram_types.get_diagram_type(body.diagram_type), body.diagram_type, de or {}, query)  # noqa: E501
    derived_entities = None if items is None else [{"id": i.entity_id, "name": i.name, "item_type": i.display_class, "role": i.role, "excluded": i.excluded} for i in items]  # noqa: E501
    return {"puml": puml, "image": image, "warnings": warnings, "derived_entities": derived_entities}


@router.post("/api/diagram", tags=[TAG_DIAGRAMS], summary="Create a diagram", response_model=OpenMapResponse)
def create_diagram_gui(body: CreateDiagramGuiBody) -> dict[str, Any]:
    from src.application.identifier_allocator import get_default_allocator
    from src.application.modeling.artifact_write import prefix_for_diagram_type
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body
    from src.infrastructure.write.artifact_write.diagram import create_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps()
    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo,
        body.entity_ids,
        body.connection_ids,
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
    )
    try:
        result = s.authorized_write(("POST", "/api/diagram"), 
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
    return s.write_result_to_dict(result)


@router.post("/api/diagram/edit", tags=[TAG_DIAGRAMS], summary="Edit a diagram", response_model=OpenMapResponse)
def edit_diagram_gui(body: EditDiagramGuiBody) -> dict[str, Any]:
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps()
    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo,
        body.entity_ids,
        body.connection_ids,
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
    )
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    try:
        result = s.authorized_write(("POST", "/api/diagram/edit"), 
            edit_diagram,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            puml=puml,
            name=body.name,
            keywords=...,
            diagram_entities=de,
            diagram_connections=dc,
            entity_ids_used=entity_ids_used,
            connection_ids_used=connection_ids_used,
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


@router.post("/api/diagram/entity-metadata", tags=[TAG_DIAGRAMS],
    summary="Patch a diagram-entity's metadata", response_model=OpenMapResponse)
def patch_diagram_entity_metadata_gui(body: PatchDiagramEntityMetadataBody) -> dict[str, Any]:
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_entity_metadata_patch import (  # noqa: PLC0415
        patch_diagram_entity_metadata,
    )

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps()
    try:
        result = s.authorized_write(("POST", "/api/diagram/entity-metadata"),
            patch_diagram_entity_metadata,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            classifier_id=body.classifier_id,
            attribute_id=body.attribute_id,
            patch=body.patch,
            dry_run=body.dry_run,
            committed_repo=committed_repository(repo),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.post("/api/matrix/preview", tags=[TAG_DIAGRAMS], summary="Preview a matrix write (dry-run)",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def preview_matrix(body: MatrixPreviewBody) -> dict[str, Any]:
    repo = s.get_repo()
    repo_root, registry, _ = s.get_write_deps()
    from src.infrastructure.write.artifact_write._matrix_content import _linkify_matrix_ids

    md = build_matrix_markdown(
        body.entity_ids,
        body.conn_type_configs,
        body.combined,
        repo,
        from_entity_ids=body.from_entity_ids,
        to_entity_ids=body.to_entity_ids,
    )
    all_ids = list(set(body.from_entity_ids or body.entity_ids) | set(body.to_entity_ids or body.entity_ids))
    linked, _ = _linkify_matrix_ids(
        repo_root=repo_root,
        registry=registry,
        matrix_markdown=md,
        candidate_entity_ids=all_ids,
    )
    return {"markdown": linked}


@router.post("/api/matrix", tags=[TAG_DIAGRAMS], summary="Create a matrix diagram", response_model=OpenMapResponse)
def create_matrix_gui(body: CreateMatrixBody) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.matrix import create_matrix

    repo = s.get_repo()
    repo_root, registry, verifier = s.get_write_deps()
    md = build_matrix_markdown(
        body.entity_ids,
        body.conn_type_configs,
        body.combined,
        repo,
        from_entity_ids=body.from_entity_ids,
        to_entity_ids=body.to_entity_ids,
    )
    try:
        result = s.authorized_write(("POST", "/api/matrix"), 
            create_matrix,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            name=body.name,
            matrix_markdown=md,
            artifact_id=None,
            keywords=body.keywords,
            version=body.version,
            status=body.status,
            entity_ids=body.entity_ids,
            from_entity_ids=body.from_entity_ids,
            to_entity_ids=body.to_entity_ids,
            conn_type_configs=body.conn_type_configs,
            combined=body.combined,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.post("/api/matrix/edit", tags=[TAG_DIAGRAMS], summary="Edit a matrix diagram", response_model=OpenMapResponse)
def edit_matrix_gui(body: EditMatrixBody) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.matrix import create_matrix

    repo = s.get_repo()
    repo_root, registry, verifier = s.get_write_deps()
    md = build_matrix_markdown(
        body.entity_ids,
        body.conn_type_configs,
        body.combined,
        repo,
        from_entity_ids=body.from_entity_ids,
        to_entity_ids=body.to_entity_ids,
    )
    diag = repo.get_diagram(body.artifact_id)
    try:
        result = s.authorized_write(("POST", "/api/matrix/edit"), 
            create_matrix,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            name=body.name,
            matrix_markdown=md,
            artifact_id=body.artifact_id,
            keywords=None,
            version=body.version or (diag.version if diag else "0.1.0"),
            status=body.status or (diag.status if diag else "draft"),
            entity_ids=body.entity_ids,
            from_entity_ids=body.from_entity_ids,
            to_entity_ids=body.to_entity_ids,
            conn_type_configs=body.conn_type_configs,
            combined=body.combined,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.post("/api/diagram/sync", tags=[TAG_DIAGRAMS], summary="Sync a diagram to the model",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def sync_diagram_to_model_gui(body: SyncDiagramToModelBody) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.diagram_sync import refresh_diagram

    repo = s.get_repo()
    repo_root, _, verifier = s.get_write_deps()
    try:
        result = s.authorized_write(("POST", "/api/diagram/sync"), 
            refresh_diagram,
            repo_root=repo_root,
            store=repo,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    d = s.write_result_to_dict(result)
    d.update(removed_entity_ids=result.removed_entity_ids, removed_connection_ids=result.removed_connection_ids)
    return d


@router.post("/api/diagram/remove", tags=[TAG_DIAGRAMS], summary="Remove a diagram", response_model=OpenMapResponse)
def delete_diagram_gui(body: DeleteDiagramBody) -> dict[str, Any]:
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_delete import delete_diagram

    repo = s.get_repo()
    repo_root, _registry, _verifier = s.get_write_deps()
    try:
        result = s.authorized_write(("POST", "/api/diagram/remove"), 
            delete_diagram,
            repo_root=repo_root,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            dry_run=body.dry_run,
            verifier=_verifier,
            committed_repo=committed_repository(repo),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)
