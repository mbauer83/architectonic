"""Translating a mutation outcome into the MCP response envelope.

One translator rather than a chain per tool: a new outcome then reaches every tool at once,
instead of falling through to the success branch in whichever tool was missed. Kept apart from the
tool registrations because it is a different job — the tools say what can be done, this says how a
result is reported — and because the registration module is at its length limit.

That promise was not kept while the parameters were typed ``Any`` and the branches were an
``isinstance`` chain: ``MutationEntityInUse`` had been a member of ``MutationResult`` and handled by
the REST adapter for some time, and this function never mentioned it, so deleting a node another
analysis referenced fell through to the success branch and raised ``AttributeError`` looking for a
payload the refusal does not have. Typing the parameter with the union and matching on it makes the
next missing case a type error instead of a crash in front of a caller.
"""

from __future__ import annotations

from src.application.assurance import analysis as analysis_uc
from src.application.assurance import mutations as mutations
from src.infrastructure.mcp.assurance_mcp import _refusals
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

#: Outcomes any assurance mutation can produce, plus the two only edge creation can.
AssuranceMutationResult = mutations.EdgeMutationResult

#: Outcomes the analysis-aggregate use cases produce.
AnalysisResult = (
    analysis_uc.AnalysisOk
    | analysis_uc.AnalysisLocked
    | analysis_uc.AnalysisNotFound
    | analysis_uc.AnalysisInvalid
    | analysis_uc.AnalysisLegacyInvalid
)


def _ok(result: mutations.MutationOk) -> dict[str, object]:
    out: dict[str, object] = dict(result.payload)
    if result.findings:
        out["verification_findings"] = result.findings
    return out


def _envelope(result: AssuranceMutationResult, ctx: AssuranceContext) -> dict[str, object]:
    """Translate any mutation outcome into the MCP response envelope.

    One translator rather than a chain per tool: a new outcome then reaches every tool at
    once, instead of falling through to the success branch in whichever tool was missed.
    """
    match result:
        case mutations.MutationLocked():
            return ctx.locked_response()
        case mutations.MutationNotFound():
            return ctx.not_found_response(result.artifact_id)
        case mutations.MutationLegacyInvalid():
            return _refusals.legacy_invalid(result.node_id, result.permitted_operation)
        case mutations.MutationRejected():
            return _refusals.rejected_field(result.field, result.message)
        case mutations.MutationEntityInUse():
            return _refusals.entity_in_use(result.node_id, list(result.referencing_analysis_ids))
        case mutations.MutationDuplicateEdge():
            return _refusals.duplicate_edge(
                result.edge_id, result.source_id, result.target_id, result.conn_type
            )
        case mutations.MutationIllegalPair():
            return _refusals.illegal_connection_type(
                result.source_type, result.target_type, result.conn_type, list(result.legal_types)
            )
        case mutations.MutationOk():
            return _ok(result)


def _analysis_result(result: AnalysisResult, ctx: AssuranceContext) -> dict[str, object]:
    match result:
        case analysis_uc.AnalysisLocked():
            return ctx.locked_response()
        case analysis_uc.AnalysisNotFound():
            return _refusals.not_found(result.analysis_id, path="analysis_id")
        case analysis_uc.AnalysisLegacyInvalid():
            return _refusals.legacy_invalid(result.node_id, result.permitted_operation)
        case analysis_uc.AnalysisInvalid():
            return _refusals.aggregate_invariant(
                result.error, result.message, subject=result.subject, count=result.count
            )
        case analysis_uc.AnalysisOk():
            return result.payload
