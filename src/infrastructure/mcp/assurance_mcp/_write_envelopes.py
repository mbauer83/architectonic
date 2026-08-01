"""Translating a mutation outcome into the MCP response envelope.

One translator rather than a chain per tool: a new outcome then reaches every tool at once,
instead of falling through to the success branch in whichever tool was missed. Kept apart from the
tool registrations because it is a different job — the tools say what can be done, this says how a
result is reported — and because the registration module is at its length limit.
"""

from __future__ import annotations

from typing import Any

from src.application.assurance import mutations as mutations
from src.application.assurance.legacy_invalid import LegacyInvalidNode


def _legacy_invalid(node_id: str, permitted_operation: str) -> dict[str, object]:
    """The refusal for a node awaiting provenance repair, in the MCP envelope.

    Names the permitted operation, because an agent told only "refused" will retry the same call.
    """
    return {
        "error": "node_legacy_invalid",
        "node_id": node_id,
        "permitted_operation": permitted_operation,
        "message": LegacyInvalidNode(node_id=node_id).message,
    }


def _ok(result: mutations.MutationOk) -> dict[str, object]:
    out: dict[str, object] = dict(result.payload)
    if result.findings:
        out["verification_findings"] = result.findings
    return out


def _envelope(result: Any, ctx: Any) -> dict[str, object]:
    """Translate any mutation outcome into the MCP response envelope.

    One translator rather than a chain per tool: a new outcome then reaches every tool at
    once, instead of falling through to the success branch in whichever tool was missed.
    """
    if isinstance(result, mutations.MutationLocked):
        return ctx.locked_response()
    if isinstance(result, mutations.MutationNotFound):
        return ctx.not_found_response(result.artifact_id)
    if isinstance(result, mutations.MutationLegacyInvalid):
        return _legacy_invalid(result.node_id, result.permitted_operation)
    if isinstance(result, mutations.MutationRejected):
        return {
            "error": "invalid_value",
            "field": result.field,
            "value": result.value,
            "message": result.message,
        }
    if isinstance(result, mutations.MutationDuplicateEdge):
        return {
            "error": "duplicate_edge",
            "edge_id": result.edge_id,
            "source_id": result.source_id,
            "target_id": result.target_id,
            "conn_type": result.conn_type,
            "message": (
                f"'{result.conn_type}' from {result.source_id} to {result.target_id} already "
                f"exists as {result.edge_id}. A second copy would state the same thing twice and "
                "be counted twice by anything that traverses it."
            ),
        }
    if isinstance(result, mutations.MutationIllegalPair):
        return {
            "error": "illegal_connection_type",
            "source_type": result.source_type,
            "target_type": result.target_type,
            "conn_type": result.conn_type,
            "legal_types": list(result.legal_types),
            "message": (
                f"'{result.conn_type}' is not a permitted edge type from "
                f"{result.source_type} to {result.target_type}. "
                + (f"Legal types for this pair: {', '.join(result.legal_types)}."
                   if result.legal_types else "No edge type is legal for this pair.")
            ),
        }
    return _ok(result)


def _analysis_result(result: Any, ctx: Any) -> dict[str, object]:
    from src.application.assurance import analysis as analysis_uc  # noqa: PLC0415

    if isinstance(result, analysis_uc.AnalysisLocked):
        return ctx.locked_response()
    if isinstance(result, analysis_uc.AnalysisNotFound):
        return ctx.not_found_response(result.analysis_id)
    if isinstance(result, analysis_uc.AnalysisInvalid):
        return {"error": result.error, "message": result.message}
    if isinstance(result, analysis_uc.AnalysisLegacyInvalid):
        return _legacy_invalid(result.node_id, result.permitted_operation)
    return result.payload


