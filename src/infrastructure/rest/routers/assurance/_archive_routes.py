"""Unlock-gated writes that record *about* the graph rather than changing its shape.

Split out of ``_assurance_write`` when that file crossed the 350-line limit, along a seam that was
already drawn in its section headings. Neither operation here adds or removes a node or an edge:

* sealing a **baseline** fixes a claim about the audit log — the sequence it reached and the hash it
  hashed to — so that anyone can re-verify it later without trusting this system's word;
* registering an **architecture reference** binds an assurance node to a model element, which is a
  statement about something outside the store entirely.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.application.assurance import mutations as mutations
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.rest.contracts.assurance_queries import (
    AssuranceArchRefRegisteredResponse,
    AssuranceBaselineSealedResponse,
)
from src.infrastructure.rest.routers._openapi import TAG_ASSURANCE_STORE
from src.infrastructure.rest.routers.assurance._write import (
    _NO_STORE,
    RegisterArchRefBody,
    SealBaselineBody,
    _locked,
    _translate,
)

archive_router = APIRouter(tags=[TAG_ASSURANCE_STORE])


# ── Baselines ─────────────────────────────────────────────────────────────────


@archive_router.post("/api/assurance/baselines", status_code=200,
    response_model=AssuranceBaselineSealedResponse)
def seal_baseline(body: SealBaselineBody) -> JSONResponse:
    """Sealing *is* creating a baseline, so it posts to the collection rather than naming the act
    in a trailing segment: there is no other way to make one, and no baseline to seal beforehand."""
    ctx = get_assurance_context()
    if not ctx.is_available():
        raise _locked()
    result = run_write(lambda: ctx.archive.seal_baseline(notes=body.notes, analysis_id=body.analysis_id))
    AssuranceBaselineSealedResponse.model_validate(result)
    return JSONResponse(content=result, headers={"Cache-Control": _NO_STORE})  # type: ignore[arg-type]


# ── Architecture references ────────────────────────────────────────────────────


@archive_router.post("/api/assurance/arch-refs", status_code=200,
    response_model=AssuranceArchRefRegisteredResponse)
def register_arch_ref(body: RegisterArchRefBody) -> JSONResponse:
    ctx = get_assurance_context()
    return _translate(run_write(lambda: mutations.register_arch_ref(
        ctx.store, ctx.archive,
        assurance_node_id=body.assurance_node_id,
        arch_artifact_id=body.arch_artifact_id,
        ref_type=body.ref_type,
    )), AssuranceArchRefRegisteredResponse)
