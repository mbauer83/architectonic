"""Response contracts for the AI-BOM surface: the scan, the role vocabulary, the export, the coverage.

Derived from ``ai_candidate_scanner.scan_candidates``, ``_aibom_exporter.AI_BOM_ROLES`` and
``aibom_service``, which returns ``asdict`` over ``application.aibom_coverage`` — so the coverage DTOs
mirror those dataclasses field for field.

Three of these routes used to answer ``200`` with an empty body and a ``note`` when the deployment had
no engagement repository configured. That is a statement about the *server*: nothing the caller sends
can fix it, and a 200 made them read the body to discover they had no answer. They raise
``not_configured`` now, the code this release reserves for exactly that — the same refusal
``gsn/rendered`` already makes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiBomCandidate(_Closed):
    """One architecture entity the scan thinks might be an AI component, and why.

    ``score`` is a heuristic rank capped at 100, and ``reasons`` is what produced it — published
    together because a suggestion an operator cannot interrogate is one they either take on faith or
    ignore. Entities already carrying an AI specialization are absent: the scan proposes marks, it does
    not re-propose the ones already made.
    """

    entity_id: str
    name: str
    entity_type: str
    score: int
    reasons: list[str]


class AiBomScanResponse(_Closed):
    """The ranked candidates, with the caveat attached to the response rather than to the docs.

    ``note`` travels in the body because this is assistive output: the surface that renders it has to
    say so where the operator is looking, not where a schema reader is.
    """

    candidates: list[AiBomCandidate]
    count: int
    note: str


class AiBomRolesResponse(_Closed):
    """The canonical derivation-role vocabulary, from the exporter that maps each role to a CycloneDX
    type. One source: a client restating it would be a second, and the export would then accept roles
    the picker never offers or offer roles it rejects."""

    roles: list[str]


class AiBomComponentCoverage(_Closed):
    """The gaps for one AI component, in two tiers.

    The split is the point. A missing REQUIRED attribute, dataset link or governance edge is
    *blocking* — the BOM is under-documented without it. A missing RECOMMENDED attribute is
    *advisory*, surfaced to help and never a validity blocker. Collapsing them into one list would
    make a wizard demand information that is optional or genuinely unavailable.

    Optional attributes are not tracked here at all, which is why there is no third list.
    """

    entity_id: str
    name: str
    specialization: str
    missing_required_attributes: list[str]
    missing_recommended_attributes: list[str]
    missing_dataset_linkage: bool
    missing_governance: bool


class AiBomCoverageResponse(_Closed):
    """Per-component gaps, plus the derivation roles nothing in the repository binds to."""

    components: list[AiBomComponentCoverage]
    unbound_roles: list[str]


class AiBomExportResponse(_Closed):
    """The ML-BOM, its size, and what is missing from it — in one response, deliberately.

    A caller emitting a BOM needs to know in the same breath what it does not document; fetching the
    coverage separately invites exporting first and asking afterwards.

    ``bom`` is a CycloneDX 1.6 document. Its vocabulary is that specification's, not this surface's, so
    it is not mirrored here — see ``contracts/open_models.py``. Mirroring it would make this package a
    second, lagging definition of a schema someone else versions.
    """

    bom: dict[str, Any]
    component_count: int
    coverage: AiBomCoverageResponse
