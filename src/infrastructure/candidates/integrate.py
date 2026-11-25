"""Integrating candidates into a new one, shared by the HTTP and MCP transports.

What is integrated and how a conflict is settled is `application/change_sets/integration.py`'s. This reads
the chosen candidates, answers the conflicts still standing with the actions each permits, and — once none
stands and it is not a dry run — stores the integration as a new draft candidate, as any candidate is
stored. Nothing is written to the model: the integration reaches it only when it is applied.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.application.change_sets.candidate_recorded_form import to_mapping
from src.application.change_sets.integration import Conflict, Resolution, integrate
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.modeling.artifact_write import generate_entity_id
from src.infrastructure.candidates.repository import KIND, CandidateConflict
from src.infrastructure.candidates.service import CandidateService


def integrate_candidates(
    service: CandidateService, ids: Sequence[str], *, name: str, rationale: str = "",
    resolutions: Sequence[Mapping[str, Any]] = (), dry_run: bool,
) -> dict[str, Any]:
    """*ids* integrated into a new draft named *name*, *resolutions* applied in order.

    A dry run answers the conflicts still standing, each with the actions it permits, and how many
    operations the integration would hold. A real integration with a conflict standing is refused (409),
    naming it; otherwise the integration is stored and answered.
    """
    chosen = [service.store.require(ref) for ref in ids]
    result = integrate(
        chosen, [_resolution(one) for one in resolutions],
        id=generate_entity_id(str(KIND.id_prefix), name), name=name, rationale=rationale,
        revision=service.index.read_model_version().etag,
    )
    answer: dict[str, Any] = {
        "candidates": [one.id for one in chosen], "dry_run": dry_run, "operations": result.operations,
        "conflicts": [_conflict(one) for one in result.conflicts],
    }
    if result.candidate is None:
        if not dry_run:
            subjects = "; ".join(f"{one.overlap.kind} about {one.overlap.subject}" for one in result.conflicts)
            raise CandidateConflict(
                f"{len(result.conflicts)} conflict{'s' if len(result.conflicts) != 1 else ''} still stand"
                f"{'s' if len(result.conflicts) == 1 else ''} ({subjects}). Resolve each — take a side, drop an "
                "operation, or merge a value — and integrate again."
            )
        return answer
    if dry_run:
        return answer
    return answer | {"integration": service.save(to_mapping(result.candidate), None)}


def _resolution(stated: Mapping[str, Any]) -> Resolution:
    return Resolution(
        kind=stated["kind"], subject=str(stated["subject"]), action=stated["action"],
        party=stated.get("party"), value=stated.get("value"),
    )


def _conflict(conflict: Conflict) -> dict[str, Any]:
    return {
        "kind": conflict.overlap.kind, "subject": conflict.overlap.subject, "actions": list(conflict.actions),
        "parties": [
            {"set_id": party.set_id, "operation": operation_to_mapping(party.operation)}
            for party in conflict.overlap.parties
        ],
    }
