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

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.application.assurance import model_bind as model_bind
from src.application.assurance import mutations as mutations
from src.application.assurance.legacy_invalid import LegacyInvalidNode
from src.application.assurance.provenance_assignment import (
    ProvenanceAnalysisNotFound,
    ProvenanceImmutable,
    ProvenanceLocked,
    ProvenanceNodeNotFound,
    assign_provenance,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.assurance.edge_legality import legal_connection_types
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.rest.contracts.assurance_nodes import (
    AssuranceEdgeCreatedResponse,
    ModelThisBoundResponse,
    ModelThisResponse,
    ModelThisTaskRequiredResponse,
)
from src.infrastructure.rest.contracts.assurance_signals import (
    AssuranceNodeCreatedResponse,
    AssuranceNodeUpdatedResponse,
)
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    DuplicateEdgeDetails,
    EntityInUseDetails,
    FieldError,
    IllegalConnectionTypeDetails,
    LegacyInvalidDetails,
    ProvenanceImmutableDetails,
    ValidationErrorDetails,
)
from src.infrastructure.rest.routers._openapi import TAG_ASSURANCE_NODES
from src.infrastructure.rest.routers.assurance._http import (
    deleted as deleted_response,
)
from src.infrastructure.rest.routers.assurance._http import (
    not_found,
    store_locked,
)
from src.infrastructure.rest.routers.assurance._invalid import bind_invalid_as_api_error
from src.infrastructure.rest.routers.entities._creator import GuiArchitectureEntityCreator

write_router = APIRouter(tags=[TAG_ASSURANCE_NODES])

_NO_STORE = "no-store"


def _locked() -> ApiError:
    """The locked refusal, in the shared envelope — returned for the caller to ``raise``.

    It used to build its own ``{"error": ...}`` body, which is the shape `CHANGELOG.md` tells
    consumers this release removed. A client branching on `detail.code` fell through on the single
    most common assurance refusal.
    """
    return store_locked()


def _not_found(artifact_id: str) -> ApiError:
    """Not-found in the shared envelope.

    The identifier does not travel in the body: the caller supplied it, so echoing it adds nothing,
    and §0e asks this surface to redact it — a not-found here is deliberately indistinguishable from
    an above-ceiling read, and a body that names the id invites the habit of trusting it.
    """
    return not_found("No such assurance record.")


def _ok(result: mutations.MutationOk, model: type[BaseModel] | None = None) -> JSONResponse:
    """A successful mutation's body, with the ``no-store`` every response on this surface carries.

    ``model`` validates the payload **and serialises it**. A raw ``JSONResponse`` is unavoidable here
    — the header is the confidentiality contract and FastAPI does not apply ``response_model`` to a
    Response the handler built — so the validation and the serialisation the framework would have done
    are both done here, which is what keeps a declared contract from being documentation of something
    nobody checked. See :func:`_http.ok` for why serialising the *payload* instead of the validated
    model is the FMEA defect's seam, on all twenty of these call sites.
    """
    out: dict[str, object] = dict(result.payload)
    if result.findings:
        out["verification_findings"] = result.findings
    if model is None:
        return JSONResponse(content=out, headers={"Cache-Control": _NO_STORE})
    return JSONResponse(
        content=model.model_validate(out).model_dump(mode="json"),
        headers={"Cache-Control": _NO_STORE},
    )


def _translate(
    result: mutations.EdgeMutationResult, model: type[BaseModel] | None = None
) -> JSONResponse:
    if isinstance(result, mutations.MutationLocked):
        raise _locked()
    if isinstance(result, mutations.MutationNotFound):
        raise _not_found(result.artifact_id)
    if isinstance(result, mutations.MutationLegacyInvalid):
        # 409, and the details name the one operation that is permitted — a caller told only
        # "refused" has no way to learn that the remedy is to assign provenance first.
        raise ApiError(
            409,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    if isinstance(result, mutations.MutationEntityInUse):
        # 409, and the details name the analyses holding the references, because the remedy is to
        # remove them and a caller told only "in use" would have to search for which.
        raise ApiError(
            409,
            "entity_in_use",
            result.message,
            EntityInUseDetails(
                node_id=result.node_id,
                referencing_analysis_ids=list(result.referencing_analysis_ids),
            ),
        )
    if isinstance(result, mutations.MutationRejected):
        # `validation_error`, not a code of its own: a rejected field value is the generic case, and
        # `FieldError` already carries the path a client highlights.
        raise ApiError(
            422,
            "validation_error",
            result.message,
            ValidationErrorDetails(
                field_errors=[FieldError(field=result.field, message=result.message)]
            ),
        )
    if isinstance(result, mutations.MutationDuplicateEdge):
        raise ApiError(
            409,
            "duplicate_edge",
            f"An edge of type {result.conn_type!r} already connects these nodes.",
            DuplicateEdgeDetails(
                edge_id=result.edge_id,
                source_id=result.source_id,
                target_id=result.target_id,
                conn_type=result.conn_type,
            ),
        )
    if isinstance(result, mutations.MutationIllegalPair):
        raise ApiError(
            422,
            "illegal_connection_type",
            f"The ontology does not permit {result.conn_type!r} from "
            f"{result.source_type!r} to {result.target_type!r}.",
            IllegalConnectionTypeDetails(
                source_type=result.source_type,
                target_type=result.target_type,
                conn_type=result.conn_type,
                legal_types=list(result.legal_types),
            ),
        )
    return _ok(result, model)


# ── Request bodies ─────────────────────────────────────────────────────────────


class CreateNodeBody(BaseModel):
    """No ``analysis_id``: creation happens *inside* an analysis, and the path names which.

    Provenance is mandatory aggregate context rather than an optional field, which is exactly why
    it cannot be a body field — an optional one is how 26 nodes came to exist with no author.
    """

    model_config = ConfigDict(extra="forbid")

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
    content_text: str = ""
    attributes: dict[str, object] | None = None


class EditNodeBody(BaseModel):
    """No ``analysis_id``: provenance is not an ordinary field, and this is not the route that
    sets it. ``PUT /api/assurance/nodes/{node_id}/provenance`` is, and only for a node that has
    none — a general edit that could silently re-attribute authorship is the gap being closed."""

    model_config = ConfigDict(extra="forbid")

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


@write_router.post("/api/assurance/analyses/{analysis_id}/nodes", status_code=201,
    response_model=AssuranceNodeCreatedResponse)
def create_node(analysis_id: str, body: CreateNodeBody, response: Response) -> JSONResponse:
    """Create a node inside the analysis that produced it.

    The analysis is the address, so provenance is recorded by construction and there is no path
    left that creates a node without it. An analysis that does not exist is a 404 rather than a
    node written with an unresolvable author.
    """
    ctx = get_assurance_context()
    if not ctx.is_available():
        raise _locked()
    if ctx.store.get_analysis(analysis_id) is None:
        raise _not_found(analysis_id)
    answer = _translate(run_write(lambda: mutations.create_node(
        ctx.store, ctx.archive,
        node_type=body.node_type, name=body.name, status=body.status, tlp=body.tlp,
        concern_class=body.concern_class, disposition=body.disposition,
        uca_type=body.uca_type, failure_type=body.failure_type, mode=body.mode,
        binding_status=body.binding_status,
        node_role=body.node_role, analysis_id=analysis_id,
        content_text=body.content_text, attributes=body.attributes,
    )), AssuranceNodeCreatedResponse)
    response.status_code = answer.status_code
    return answer


class AssignProvenanceBody(BaseModel):
    """The analysis that produced this node. The node is the path; this is the assertion."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str


@write_router.put("/api/assurance/nodes/{node_id}/provenance", status_code=204,
    response_model=None)
def assign_node_provenance(node_id: str, body: AssignProvenanceBody) -> None:
    """Record which analysis produced a node. The only route that may set provenance.

    Idempotent: re-asserting the same analysis answers 204 and writes nothing. Asserting a
    different one is refused — an analysis's output is a historical fact, and moving a node between
    analyses would rewrite what each of them is on record as having found.
    """
    ctx = get_assurance_context()
    result = run_write(lambda: assign_provenance(
        ctx.store, ctx.archive, node_id=node_id, analysis_id=body.analysis_id,
    ))
    if isinstance(result, ProvenanceLocked):
        raise store_locked()
    if isinstance(result, ProvenanceNodeNotFound):
        raise not_found(f"no node {result.node_id!r}")
    if isinstance(result, ProvenanceAnalysisNotFound):
        raise not_found(f"no analysis {result.analysis_id!r}")
    if isinstance(result, ProvenanceImmutable):
        raise ApiError(
            409,
            "provenance_immutable",
            "this node already records which analysis produced it",
            ProvenanceImmutableDetails(
                node_id=result.node_id, current_analysis_id=result.current_analysis_id,
            ),
        )


@write_router.patch("/api/assurance/nodes/{node_id}", status_code=200,
    response_model=AssuranceNodeUpdatedResponse)
def edit_node(node_id: str, body: EditNodeBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.edit_node(
        ctx.store, ctx.archive,
        node_id=node_id, name=body.name, status=body.status, tlp=body.tlp,
        concern_class=body.concern_class, disposition=body.disposition,
        uca_type=body.uca_type, failure_type=body.failure_type, mode=body.mode,
        binding_status=body.binding_status,
        node_role=body.node_role, content_text=body.content_text,
        attributes=body.attributes,
    )), AssuranceNodeUpdatedResponse)


@write_router.delete("/api/assurance/nodes/{node_id}", status_code=204, response_model=None)
def delete_node(node_id: str) -> Response:
    ctx = get_assurance_context()
    return deleted_response(
        _translate(run_write(lambda: mutations.delete_node(ctx.store, ctx.archive, node_id=node_id)))
    )


# ── Edge endpoints ─────────────────────────────────────────────────────────────


@write_router.post("/api/assurance/edges", status_code=200,
    response_model=AssuranceEdgeCreatedResponse)
def add_edge(body: AddEdgeBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.add_edge(
        ctx.store, ctx.archive,
        source_id=body.source_id, target_id=body.target_id,
        conn_type=body.conn_type, attributes=body.attributes,
        legal_connection_types=legal_connection_types,
    )), AssuranceEdgeCreatedResponse)


@write_router.delete("/api/assurance/edges/{edge_id}", status_code=204, response_model=None)
def delete_edge(edge_id: str) -> Response:
    ctx = get_assurance_context()
    return deleted_response(
        _translate(run_write(lambda: mutations.delete_edge(ctx.store, ctx.archive, edge_id=edge_id)))
    )


# ── Model-this (create+bind, or task for an architecture-write session) ───────────


def _translate_bind(result: model_bind.ModelBindResult) -> JSONResponse:
    if isinstance(result, model_bind.BindLocked):
        raise _locked()
    if isinstance(result, model_bind.BindNotFound):
        raise _not_found(result.assurance_node_id)
    if isinstance(result, model_bind.BindInvalid):
        raise bind_invalid_as_api_error(result)
    if isinstance(result, model_bind.TaskRequired):
        handover: dict[str, object] = {"outcome": "task_required", **result.spec}
        ModelThisTaskRequiredResponse.model_validate(handover)
        return JSONResponse(content=handover, headers={"Cache-Control": _NO_STORE})
    payload: dict[str, object] = {
        "outcome": "bound",
        "assurance_node_id": result.assurance_node_id,
        "arch_artifact_id": result.arch_artifact_id,
    }
    if result.findings:
        payload["verification_findings"] = result.findings
    ModelThisBoundResponse.model_validate(payload)
    return JSONResponse(content=payload, headers={"Cache-Control": _NO_STORE})


@write_router.post("/api/assurance/model-this", status_code=200,
    response_model=ModelThisResponse)
def model_this(
    body: ModelThisBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> JSONResponse:
    ctx = get_assurance_context()
    if not ctx.is_available():
        raise _locked()
    creator = None if body.separation_of_duties else GuiArchitectureEntityCreator(catalogs)
    result = run_write(lambda: model_bind.model_and_bind(
        ctx.store, ctx.archive,
        assurance_node_id=body.assurance_node_id,
        suggested_arch_type=body.suggested_arch_type,
        suggested_name=body.suggested_name,
        domain=body.domain,
        arch_creator=creator,
    ))
    return _translate_bind(result)


