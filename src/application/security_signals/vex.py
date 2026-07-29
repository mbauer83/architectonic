"""Audited VEX mutation use case.

One immutable revision per call, validated by the domain rules (suppressing
statuses require a justification; author required), keyed run-independently
by (anchor, canonical component incl. version, canonical vulnerability). The
store lands the revision and its audit record in one transaction. Alias merges
repoint assessment history without losing it (store-side).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.domain.assurance.vex_assessment import VexValidationError, validate_assessment


class VexWriteStore(Protocol):
    def record_vex_assessment(
        self,
        *,
        anchor_entity_id: str,
        canonical_component_id: str,
        canonical_vulnerability_id: str,
        vex_status: str,
        justification: str,
        author: str,
        source: str = "",
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RecordVexRequest:
    anchor_entity_id: str
    canonical_component_id: str  # includes the exact version (purl form)
    canonical_vulnerability_id: str
    vex_status: str
    justification: str
    author: str
    source: str = ""


@dataclass(frozen=True)
class VexRecorded:
    assessment_id: str
    revision: int
    created_at: str


@dataclass(frozen=True)
class VexInvalid:
    errors: tuple[VexValidationError, ...]


VexResult = VexRecorded | VexInvalid


def record_vex_assessment(request: RecordVexRequest, *, store: VexWriteStore) -> VexResult:
    errors = list(validate_assessment(request.vex_status, request.justification, request.author))
    for field_name in ("anchor_entity_id", "canonical_component_id", "canonical_vulnerability_id"):
        if not getattr(request, field_name).strip():
            errors.append(VexValidationError(field=field_name, message=f"{field_name} is required"))
    if errors:
        return VexInvalid(errors=tuple(errors))
    row = store.record_vex_assessment(
        anchor_entity_id=request.anchor_entity_id,
        canonical_component_id=request.canonical_component_id,
        canonical_vulnerability_id=request.canonical_vulnerability_id,
        vex_status=request.vex_status,
        justification=request.justification,
        author=request.author,
        source=request.source,
    )
    return VexRecorded(
        assessment_id=str(row["assessment_id"]),
        revision=int(row["revision"]),  # type: ignore[call-overload]
        created_at=str(row["created_at"]),
    )
