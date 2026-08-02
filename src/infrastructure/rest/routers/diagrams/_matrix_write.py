"""Matrix write endpoints.

A matrix is a diagram of the matrix kind, but it is created and replaced through its own request
contract — entity ids and connection-type configurations rather than a PUML body — so it is
addressed under ``/api/matrices`` and served from its own module. Split from the diagram writes when
that file passed the size limit; the seam is the contract, not the storage.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from src.infrastructure.rest.contracts.diagrams import MatrixPreviewResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import TAG_DIAGRAMS, WRITE_RESPONSES, WriteResultResponse
from src.infrastructure.rest.routers.diagrams._matrix_markdown import build_matrix_markdown
from src.infrastructure.rest.routers.diagrams._write_bodies import (
    CreateMatrixBody,
    EditMatrixBody,
    MatrixPreviewBody,
)
from src.infrastructure.rest.routers.diagrams._write_responses import (
    CREATE_RESPONSES,
    DETAIL_RESPONSES,
    created,
)

router = APIRouter(responses=WRITE_RESPONSES)


@router.post("/api/matrices/preview", tags=[TAG_DIAGRAMS], summary="Preview a matrix write (dry-run)",
    response_model=MatrixPreviewResponse, responses=WRITE_RESPONSES)
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


@router.post("/api/matrices", tags=[TAG_DIAGRAMS], summary="Create a matrix diagram",
    response_model=WriteResultResponse, responses=CREATE_RESPONSES, status_code=status.HTTP_201_CREATED)
def create_matrix_gui(body: CreateMatrixBody, response: Response) -> dict[str, Any]:
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
        result = s.authorized_write(
            "matrices_create_matrix", 
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
    created(result, response, f"/api/matrices/{result.artifact_id}")
    return s.write_result_to_dict(result)


@router.put("/api/matrices/{artifact_id}", tags=[TAG_DIAGRAMS], summary="Replace a matrix diagram",
    response_model=WriteResultResponse, responses=DETAIL_RESPONSES)
def edit_matrix_gui(artifact_id: str, body: EditMatrixBody) -> dict[str, Any]:
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
    diag = repo.get_diagram(artifact_id)
    try:
        result = s.authorized_write(
            "matrices_replace_matrix", 
            create_matrix,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            name=body.name,
            matrix_markdown=md,
            artifact_id=artifact_id,
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
