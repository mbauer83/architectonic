"""binding_proposals.py — Build enriched binding proposals from model ids + allowed_bindings.

Proposal-only: no writes. Used by the propose-bindings mode and by graph traversal tools
when a diagram_type context is provided. Consumers echo the result to apply-diff or use
the suggested kinds when calling create/edit diagram with bindings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.derivation.types import ModelQuery
    from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec


def _entity_candidates(entity_type: str, spec: AllowedBindingsSpec) -> list[dict[str, object]]:
    """Return diagram entity types admissible for an entity-id target, with default kinds."""
    candidates: list[dict[str, object]] = []
    for dtype, espec in spec.entity.items():
        if "entity-id" not in espec.target_forms:
            continue
        candidates.append({
            "diagram_entity_type": dtype,
            "default_correspondence_kind": espec.default_correspondence_kind,
            "admissible_correspondence_kinds": list(espec.correspondence_kinds),
        })
    return candidates


def _connection_candidates(conn_type: str, spec: AllowedBindingsSpec) -> list[dict[str, object]]:
    """Return diagram connection types admissible for a connection-id target, with default kinds."""
    candidates: list[dict[str, object]] = []
    for dtype, cspec in spec.connection.items():
        has_id_form = "connection-id" in cspec.target_forms or "connection-ids" in cspec.target_forms
        if not has_id_form:
            continue
        type_ok = (
            not cspec.target_connection_types
            or conn_type in cspec.target_connection_types
        )
        if not type_ok:
            continue
        candidates.append({
            "diagram_connection_type": dtype,
            "default_correspondence_kind": cspec.default_correspondence_kind,
            "admissible_correspondence_kinds": list(cspec.correspondence_kinds),
        })
    return candidates


def build_entity_proposals(
    entity_ids: list[str],
    allowed_bindings: AllowedBindingsSpec,
    query: ModelQuery,
) -> list[dict[str, object]]:
    """Build enriched entity binding proposals.

    Each proposal includes the model name, type, and candidate diagram entity types
    with their default and admissible correspondence kinds. Proposals for unknown
    entity ids are still returned (model_name/type = None) so callers know what
    was missing.
    """
    out: list[dict[str, object]] = []
    for eid in entity_ids:
        record = query.get_entity(eid)
        proposal: dict[str, object] = {"model_entity_id": eid}
        if record is not None:
            proposal["model_name"] = record.name
            proposal["model_type"] = record.artifact_type
            proposal["candidate_diagram_types"] = _entity_candidates(record.artifact_type, allowed_bindings)
        else:
            proposal["candidate_diagram_types"] = _entity_candidates("", allowed_bindings)
        out.append(proposal)
    return out


def build_connection_proposals(
    connection_ids: list[str],
    allowed_bindings: AllowedBindingsSpec,
    query: ModelQuery,
) -> list[dict[str, object]]:
    """Build enriched connection binding proposals."""
    out: list[dict[str, object]] = []
    for cid in connection_ids:
        record = query.get_connection(cid)
        proposal: dict[str, object] = {"model_connection_id": cid}
        if record is not None:
            proposal["model_connection_type"] = record.conn_type
            proposal["candidate_diagram_types"] = _connection_candidates(record.conn_type, allowed_bindings)
        else:
            proposal["candidate_diagram_types"] = _connection_candidates("", allowed_bindings)
        out.append(proposal)
    return out


def entity_binding_guidance(entity_type: str, allowed_bindings: AllowedBindingsSpec) -> list[dict[str, object]]:
    """Return binding guidance for a model entity type in a given diagram type context.

    Used by graph traversal tools when annotating neighbour results with binding
    proposals. Returns the same candidate_diagram_types shape as build_entity_proposals.
    """
    return _entity_candidates(entity_type, allowed_bindings)
