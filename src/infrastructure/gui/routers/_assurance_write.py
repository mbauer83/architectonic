"""Unlock-gated HTTP write endpoints for the confidential assurance store.

All mutation endpoints share one pattern:
  1. Build an AssuranceMutationPolicy from the current context.
  2. Check locked → 423.
  3. Call the shared application use case (assurance_mutations).
  4. Translate the mutation outcome to HTTP.
  5. Return with Cache-Control: no-store.

Response semantics:
  - Locked store        → 423 Locked
  - Node/edge not found → 404
  - Value outside a closed vocabulary → 422
  - Write TLP > ceiling → 403 (ForbiddenWrite, writes only)
  - Success             → 200 with payload + optional verification_findings
  - All responses       → Cache-Control: no-store
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application import assurance_model_bind as model_bind
from src.application import assurance_mutations as mutations
from src.infrastructure.assurance.edge_legality import legal_connection_types
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.routers._arch_entity_creator import GuiArchitectureEntityCreator
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context

write_router = APIRouter()

_NO_STORE = "no-store"


def _locked() -> JSONResponse:
    return JSONResponse(
        status_code=423,
        content={"error": "assurance_store_locked", "message": (
            "The confidential assurance store is not unlocked. "
            "Run `arch-assurance unlock` to enable assurance tools."
        )},
        headers={"Cache-Control": _NO_STORE},
    )


def _not_found(artifact_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "not_found", "artifact_id": artifact_id},
        headers={"Cache-Control": _NO_STORE},
    )


def _ok(result: mutations.MutationOk) -> JSONResponse:
    out: dict[str, object] = dict(result.payload)
    if result.findings:
        out["verification_findings"] = result.findings
    return JSONResponse(content=out, headers={"Cache-Control": _NO_STORE})


def _translate(result: mutations.EdgeMutationResult) -> JSONResponse:
    if isinstance(result, mutations.MutationLocked):
        return _locked()
    if isinstance(result, mutations.MutationNotFound):
        return _not_found(result.artifact_id)
    if isinstance(result, mutations.MutationRejected):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_value",
                "field": result.field,
                "value": result.value,
                "message": result.message,
            },
            headers={"Cache-Control": _NO_STORE},
        )
    if isinstance(result, mutations.MutationDuplicateEdge):
        return JSONResponse(
            status_code=409,
            content={
                "error": "duplicate_edge",
                "edge_id": result.edge_id,
                "source_id": result.source_id,
                "target_id": result.target_id,
                "conn_type": result.conn_type,
            },
            headers={"Cache-Control": _NO_STORE},
        )
    if isinstance(result, mutations.MutationIllegalPair):
        return JSONResponse(
            status_code=422,
            content={
                "error": "illegal_connection_type",
                "source_type": result.source_type,
                "target_type": result.target_type,
                "conn_type": result.conn_type,
                "legal_types": list(result.legal_types),
            },
            headers={"Cache-Control": _NO_STORE},
        )
    return _ok(result)



# ── Request bodies ─────────────────────────────────────────────────────────────


class CreateNodeBody(BaseModel):
    node_type: str
    name: str
    status: str = "draft"
    tlp: str = "TLP:WHITE"
    concern_class: str | None = None
    disposition: str | None = None
    uca_type: str | None = None
    failure_type: str | None = None
    mode: str | None = None
    binding_status: str | None = None
    node_role: str | None = None
    analysis_id: str | None = None
    content_text: str = ""
    attributes: dict[str, object] | None = None


class EditNodeBody(BaseModel):
    name: str | None = None
    status: str | None = None
    tlp: str | None = None
    concern_class: str | None = None
    disposition: str | None = None
    uca_type: str | None = None
    failure_type: str | None = None
    mode: str | None = None
    binding_status: str | None = None
    node_role: str | None = None
    content_text: str | None = None
    attributes: dict[str, object] | None = None
    #: Re-attributes authorship. Every node is supposed to belong to an analysis, and one authored
    #: before the analysis aggregate existed does not — so this has to be settable, or the invariant
    #: is unfixable. Validated against the analyses that exist.
    analysis_id: str | None = None


class AddEdgeBody(BaseModel):
    source_id: str
    target_id: str
    conn_type: str
    attributes: dict[str, object] | None = None


class SealBaselineBody(BaseModel):
    notes: str = ""
    analysis_id: str | None = None


class RegisterArchRefBody(BaseModel):
    assurance_node_id: str
    arch_artifact_id: str
    ref_type: str


class ModelThisBody(BaseModel):
    assurance_node_id: str
    suggested_arch_type: str
    suggested_name: str
    domain: str = "application"
    # When true, do not create the architecture entity here — return a task for an
    # architecture-write session (separation of duties).
    separation_of_duties: bool = False


# ── Node endpoints ─────────────────────────────────────────────────────────────


@write_router.post("/api/assurance/nodes", status_code=200)
def create_node(body: CreateNodeBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.create_node(
        ctx.store, ctx.archive,
        node_type=body.node_type, name=body.name, status=body.status, tlp=body.tlp,
        concern_class=body.concern_class, disposition=body.disposition,
        uca_type=body.uca_type, failure_type=body.failure_type, mode=body.mode,
        binding_status=body.binding_status,
        node_role=body.node_role, analysis_id=body.analysis_id,
        content_text=body.content_text, attributes=body.attributes,
    )))


@write_router.patch("/api/assurance/nodes/{node_id}", status_code=200)
def edit_node(node_id: str, body: EditNodeBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.edit_node(
        ctx.store, ctx.archive,
        node_id=node_id, name=body.name, status=body.status, tlp=body.tlp,
        concern_class=body.concern_class, disposition=body.disposition,
        uca_type=body.uca_type, failure_type=body.failure_type, mode=body.mode,
        binding_status=body.binding_status,
        node_role=body.node_role, content_text=body.content_text,
        attributes=body.attributes, analysis_id=body.analysis_id,
    )))


@write_router.delete("/api/assurance/nodes/{node_id}", status_code=200)
def delete_node(node_id: str) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.delete_node(ctx.store, ctx.archive, node_id=node_id)))


# ── Edge endpoints ─────────────────────────────────────────────────────────────


@write_router.post("/api/assurance/edges", status_code=200)
def add_edge(body: AddEdgeBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.add_edge(
        ctx.store, ctx.archive,
        source_id=body.source_id, target_id=body.target_id,
        conn_type=body.conn_type, attributes=body.attributes,
        legal_connection_types=legal_connection_types,
    )))


@write_router.delete("/api/assurance/edges/{edge_id}", status_code=200)
def delete_edge(edge_id: str) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.delete_edge(ctx.store, ctx.archive, edge_id=edge_id)))


# ── Baselines ─────────────────────────────────────────────────────────────────


@write_router.post("/api/assurance/baselines/seal", status_code=200)
def seal_baseline(body: SealBaselineBody) -> JSONResponse:
    ctx = get_assurance_context()
    if not ctx.is_available():
        return _locked()
    result = run_write(lambda: ctx.archive.seal_baseline(notes=body.notes, analysis_id=body.analysis_id))
    return JSONResponse(content=result, headers={"Cache-Control": _NO_STORE})  # type: ignore[arg-type]


# ── Architecture references ────────────────────────────────────────────────────


@write_router.post("/api/assurance/arch-refs", status_code=200)
def register_arch_ref(body: RegisterArchRefBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.register_arch_ref(
        ctx.store, ctx.archive,
        assurance_node_id=body.assurance_node_id,
        arch_artifact_id=body.arch_artifact_id,
        ref_type=body.ref_type,
    )))


# ── Model-this (create+bind, or task for an architecture-write session) ───────────


def _translate_bind(result: model_bind.ModelBindResult) -> JSONResponse:
    if isinstance(result, model_bind.BindLocked):
        return _locked()
    if isinstance(result, model_bind.BindNotFound):
        return _not_found(result.assurance_node_id)
    if isinstance(result, model_bind.BindInvalid):
        status = 409 if result.error == "invalid_binding_status" else 400
        return JSONResponse(
            status_code=status,
            content={"error": result.error, "message": result.message},
            headers={"Cache-Control": _NO_STORE},
        )
    if isinstance(result, model_bind.TaskRequired):
        return JSONResponse(
            content={"outcome": "task_required", **result.spec},
            headers={"Cache-Control": _NO_STORE},
        )
    payload: dict[str, object] = {
        "outcome": "bound",
        "assurance_node_id": result.assurance_node_id,
        "arch_artifact_id": result.arch_artifact_id,
    }
    if result.findings:
        payload["verification_findings"] = result.findings
    return JSONResponse(content=payload, headers={"Cache-Control": _NO_STORE})


@write_router.post("/api/assurance/model-this", status_code=200)
def model_this(body: ModelThisBody) -> JSONResponse:
    ctx = get_assurance_context()
    if not ctx.is_available():
        return _locked()
    creator = None if body.separation_of_duties else GuiArchitectureEntityCreator()
    result = run_write(lambda: model_bind.model_and_bind(
        ctx.store, ctx.archive,
        assurance_node_id=body.assurance_node_id,
        suggested_arch_type=body.suggested_arch_type,
        suggested_name=body.suggested_name,
        domain=body.domain,
        arch_creator=creator,
    ))
    return _translate_bind(result)


