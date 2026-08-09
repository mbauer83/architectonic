"""The MCP repair path for a node's provenance.

Split from the other write tools so the state machine's reasoning sits in one place, and because
the write-tools module passed the size limit. The rule it enforces is the same one the REST route
enforces, through the same use case: provenance is set once, by a person, for a node that has none.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance.provenance_assignment import (
    ProvenanceAnalysisNotFound,
    ProvenanceImmutable,
    ProvenanceLocked,
    ProvenanceNodeNotFound,
    assign_provenance,
)
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp import _refusals
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.tool_annotations import IDEMPOTENT_LOCAL_WRITE


def register_provenance_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_assign_provenance",
        description=(
            "Record which analysis produced a node — the ONLY way to set provenance, and only for "
            "a node that has none. Nodes authored before the analysis aggregate existed carry no "
            "provenance, and this repairs them one at a time, audited. Re-asserting the same "
            "analysis is idempotent; asserting a different one is refused, because an analysis's "
            "output is a historical fact and moving a node would rewrite what each analysis is on "
            "record as having found. Automatic attribution is deliberately not offered: a guess "
            "recorded as provenance cannot afterwards be told apart from a real attribution."
        ),
        annotations=IDEMPOTENT_LOCAL_WRITE,
    )
    def assurance_assign_provenance(node_id: str, analysis_id: str) -> dict[str, object]:
        result = run_write(lambda: assign_provenance(
            ctx.store, ctx.archive, node_id=node_id, analysis_id=analysis_id,
        ))
        match result:
            case ProvenanceLocked():
                return ctx.locked_response()
            case ProvenanceNodeNotFound():
                return _refusals.not_found(result.node_id)
            case ProvenanceAnalysisNotFound():
                return _refusals.not_found(result.analysis_id, path="analysis_id")
            case ProvenanceImmutable():
                return _refusals.provenance_immutable(result.node_id, result.current_analysis_id)
        return {
            "node_id": result.node_id,
            "analysis_id": result.analysis_id,
            "recorded": result.recorded,
        }