"""HTTP read endpoints for AI-BOM candidate scanning, role vocabulary, and ML-BOM export.

These capabilities are pure transforms / public-model reads (no confidential store access),
so they get a dedicated router (keeps _assurance_read.py within its size budget):

  GET  /api/assurance/aibom/scan      — heuristic AI-candidate scan over the *public*
                                         architecture repository (un-gated: touches no
                                         confidential content, only ranks model entities).
  GET  /api/assurance/aibom/roles     — canonical AI-BOM role vocabulary (single backend
                                         source of truth; the GUI consumes this rather than
                                         redeclaring the enum).
  POST /api/assurance/aibom/export    — emit a CycloneDX 1.6 ML-BOM derived from the model.
                                         Not from caller-confirmed components, as this line
                                         once said: the model is the source of truth, and the
                                         body carries only the note to stamp on the result.

All responses carry ``Cache-Control: no-store``.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.infrastructure.gui.contracts.assurance_aibom import (
    AiBomCoverageResponse,
    AiBomExportResponse,
    AiBomRolesResponse,
    AiBomScanResponse,
)
from src.infrastructure.gui.contracts.errors import ApiError, NotConfiguredDetails
from src.infrastructure.gui.routers._assurance_http import ok as _ok

aibom_router = APIRouter()


class AiBomExportBody(BaseModel):
    """What to stamp on the exported BOM. The components are not a caller's to supply.

    Was ``dict[str, object]`` via ``Body(default={})`` — the last untyped request body on this surface,
    and one that read as though a caller could hand over a component list. It cannot: the export is
    derived from the architecture model, which is the whole point of it being trustworthy, and the only
    thing left for a request to say is what note to record alongside.
    """

    model_config = ConfigDict(extra="forbid")

    notes: str = ""


def _repository_required() -> ApiError:
    """The refusal for a deployment with no engagement repository configured.

    These three routes used to answer 200 with an empty BOM and a ``note``, which made a caller read
    the body to learn they had no answer — and made "nothing to export" indistinguishable from "no
    repository to export from". A statement about the server is neither a conflict nor a validation
    error: nothing the caller sends can fix it.
    """
    return ApiError(
        500,
        "not_configured",
        "No engagement repository is configured, so there is no model to derive an AI-BOM from.",
        NotConfiguredDetails(
            capability="engagement-repository",
            remedy="Start the backend with an engagement repository root.",
        ),
    )


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


@aibom_router.get("/api/assurance/aibom/scan", response_model=AiBomScanResponse)
def aibom_scan_candidates(domain: str | None = None, limit: int = 50) -> JSONResponse:
    """Rank public architecture model entities by AI-BOM relevance (assistive only)."""
    from src.infrastructure.assurance.ai_candidate_scanner import scan_candidates  # noqa: PLC0415
    from src.infrastructure.gui.routers import state as s  # noqa: PLC0415

    repo = s.maybe_get_repo()
    if repo is None:
        raise _repository_required()
    entities: list[dict[str, object]] = [
        {
            "entity_id": e.artifact_id,
            "name": e.name,
            "entity_type": e.artifact_type,
            "description": e.content_text,
            # Carried so the scan skips entities already marked with an AI specialization.
            "specializations": list(e.specializations),
        }
        for e in repo.list_entities(domain=domain)
        if e.host_diagram_id is None  # model entities only; not diagram-only nodes
    ]
    candidates = scan_candidates(entities)[: max(limit, 0)]
    return _ok(
        {"candidates": candidates, "count": len(candidates), "note": _SCAN_NOTE},
        AiBomScanResponse,
    )


@aibom_router.get("/api/assurance/aibom/roles", response_model=AiBomRolesResponse)
def aibom_roles() -> JSONResponse:
    """Canonical AI-BOM role vocabulary (single backend source; GUI consumes this)."""
    from src.infrastructure.assurance._aibom_exporter import AI_BOM_ROLES  # noqa: PLC0415

    return _ok({"roles": list(AI_BOM_ROLES)}, AiBomRolesResponse)


@aibom_router.post("/api/assurance/aibom/export", response_model=AiBomExportResponse)
def aibom_export(body: AiBomExportBody = AiBomExportBody()) -> JSONResponse:
    """Emit a CycloneDX 1.6 ML-BOM DERIVED from the architecture model — every entity carrying
    an AI specialization, with its model card, dataset/governance links, and dependency graph.
    No caller-supplied component list: the model is the source of truth."""
    from src.infrastructure.assurance.aibom_service import export_model_derived_aibom  # noqa: PLC0415
    from src.infrastructure.gui.routers import state as s  # noqa: PLC0415

    repo = s.maybe_get_repo()
    repo_root = s.maybe_engagement_root()
    if repo is None or repo_root is None:
        raise _repository_required()
    return _ok(
        export_model_derived_aibom(repo, repo_root, _catalogs(), notes=body.notes),
        AiBomExportResponse,
    )


@aibom_router.get("/api/assurance/aibom/coverage", response_model=AiBomCoverageResponse)
def aibom_coverage() -> JSONResponse:
    """Per-AI-component coverage: blocking gaps (missing required attributes, dataset link,
    governance) vs advisory (recommended), plus repo-wide unbound derivation roles."""
    from src.infrastructure.assurance.aibom_service import aibom_coverage_report  # noqa: PLC0415
    from src.infrastructure.gui.routers import state as s  # noqa: PLC0415

    repo = s.maybe_get_repo()
    repo_root = s.maybe_engagement_root()
    if repo is None or repo_root is None:
        raise _repository_required()
    return _ok(aibom_coverage_report(repo, repo_root, _catalogs()), AiBomCoverageResponse)


_SCAN_NOTE = (
    "Heuristic suggestions only — confirm each candidate before exporting it as an "
    "AI component. The scan ranks architecture model entities by name/type patterns."
)
