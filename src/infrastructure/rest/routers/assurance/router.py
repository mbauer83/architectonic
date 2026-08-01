"""Backend endpoints for the assurance module.

Includes:
  - Store status / reload (always callable)
  - Unlock-gated read endpoints (nodes, edges, stats, coverage, verify,
    risk-register, BOM/vuln, baselines, architecture lens) — via _assurance_read.
  - Unlock-gated write endpoints (create/edit/delete nodes, edges, arch-refs,
    baselines, model-this, BOM/vuln/anchor imports) — via _assurance_write.
  - AI-BOM coverage / candidate scan / ML-BOM export — via _assurance_aibom.
  - Failure-mode factor judgements — via _assurance_fmea_routes.
  - Groups, filing and participation — via _assurance_grouping_routes.
  - Analysis-scoped derived diagrams — via _assurance_diagram_routes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance.edge_catalog import build_edge_catalog
from src.infrastructure.app_bootstrap import assurance_ontology_module, get_module_registry
from src.infrastructure.rest.contracts.assurance_nodes import AssuranceEdgeCatalogResponse
from src.infrastructure.rest.contracts.assurance_store import AssuranceStoreStatusResponse
from src.infrastructure.rest.contracts.errors import ApiError, NotConfiguredDetails
from src.infrastructure.rest.routers.assurance._aibom import aibom_router
from src.infrastructure.rest.routers.assurance._analysis_routes import analysis_router
from src.infrastructure.rest.routers.assurance._archive_routes import archive_router
from src.infrastructure.rest.routers.assurance._diagram_routes import diagram_router
from src.infrastructure.rest.routers.assurance._fmea_routes import fmea_router
from src.infrastructure.rest.routers.assurance._grouping_routes import grouping_router
from src.infrastructure.rest.routers.assurance._gsn_routes import gsn_router
from src.infrastructure.rest.routers.assurance._neighbors_routes import neighbors_router
from src.infrastructure.rest.routers.assurance._read import read_router
from src.infrastructure.rest.routers.assurance._signal_deletion_routes import (
    signal_deletion_router,
)
from src.infrastructure.rest.routers.assurance._signals_routes import signals_router
from src.infrastructure.rest.routers.assurance._write import write_router

router = APIRouter()
router.include_router(read_router)
router.include_router(neighbors_router)
router.include_router(signals_router)
router.include_router(signal_deletion_router)
router.include_router(write_router)
router.include_router(archive_router)
router.include_router(analysis_router)
router.include_router(gsn_router)
router.include_router(grouping_router)
router.include_router(diagram_router)
router.include_router(aibom_router)
router.include_router(fmea_router)

_DEFAULT_DB = Path(__file__).resolve().parents[4] / ".arch-assurance" / "store.db"


class AssuranceReloadBody(BaseModel):
    """`authorize` carries the operator's intent, which the policy alone cannot express.

    None leaves this process's authorization as it is — the case for a reload after the store
    was re-keyed. True is `unlock` authorizing the running process; False is `lock` revoking it.
    """

    authorize: bool | None = None


@router.post("/api/assurance/reload", status_code=200,
    response_model=AssuranceStoreStatusResponse)
def assurance_reload(body: AssuranceReloadBody | None = None) -> dict[str, object]:
    """Evict the assurance bundle cache and rebuild it, applying the activation policy.

    Called by `arch-assurance unlock` and `lock` so the running backend reflects the change at
    once. Under the manual activation policy this is what makes `unlock` do something: a
    rebuild alone would re-apply the policy and start locked again, so the command would appear
    to succeed and change nothing.
    """
    from src.infrastructure.assurance import store_factory  # noqa: PLC0415
    from src.infrastructure.mcp.assurance_mcp.context import clear_context_cache  # noqa: PLC0415

    intent = body.authorize if body is not None else None
    if intent is True:
        store_factory.authorize_process()
    elif intent is False:
        store_factory.revoke_process_authorization()

    clear_context_cache()
    # Eagerly rebuild so the response reflects the new state.
    return assurance_status()


@router.get("/api/assurance/edge-catalog", response_model=AssuranceEdgeCatalogResponse)
def assurance_edge_catalog() -> JSONResponse:
    """Edge and reference type catalog from the loaded assurance module.

    Configured-gated but NOT unlock-gated: it serves module configuration,
    never store content. Registry enablement (capability present) is the gate.
    """
    if get_module_registry().find_ontology("assurance") is None:
        raise ApiError(
            404,
            "not_configured",
            "The assurance module is not configured for this deployment.",
            NotConfiguredDetails(
                capability="assurance",
                remedy="Enable the assurance module in config/settings.yaml.",
            ),
        )
    catalog = build_edge_catalog(assurance_ontology_module())
    AssuranceEdgeCatalogResponse.model_validate(catalog)
    return JSONResponse(content=catalog)


@router.get("/api/assurance/status", response_model=AssuranceStoreStatusResponse)
def assurance_status() -> dict[str, object]:
    """Return confidential assurance store configuration and lock status.

    Always callable — does not require the store to be unlocked.
    Used by the frontend to show the locked/unlocked banner.
    """
    try:
        from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

        key_present = accounts.present(accounts.DB_KEY, _DEFAULT_DB)
    except Exception:  # noqa: BLE001
        key_present = False

    db_exists = _DEFAULT_DB.exists()
    configured = db_exists and key_present

    try:
        from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context  # noqa: PLC0415

        unlocked = get_assurance_context().is_available()
    except Exception:  # noqa: BLE001
        unlocked = False

    if unlocked:
        store_status = "unlocked"
    elif configured:
        store_status = "locked"
    else:
        store_status = "not_initialised"

    return {
        "configured": configured,
        "unlocked": unlocked,
        "db_exists": db_exists,
        "key_in_keychain": key_present,
        "status": store_status,
        "module_class": "assurance",
    }
