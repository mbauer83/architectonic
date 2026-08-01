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
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context


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
    )
    def assurance_assign_provenance(node_id: str, analysis_id: str) -> dict[str, object]:
        result = run_write(lambda: assign_provenance(
            ctx.store, ctx.archive, node_id=node_id, analysis_id=analysis_id,
        ))
        if isinstance(result, ProvenanceLocked):
            return {"error": "assurance_store_locked"}
        if isinstance(result, ProvenanceNodeNotFound):
            return {"error": "not_found", "node_id": result.node_id}
        if isinstance(result, ProvenanceAnalysisNotFound):
            return {"error": "not_found", "analysis_id": result.analysis_id}
        if isinstance(result, ProvenanceImmutable):
            return {
                "error": "provenance_immutable",
                "node_id": result.node_id,
                "current_analysis_id": result.current_analysis_id,
                "message": (
                    "This node already records which analysis produced it. Provenance is "
                    "immutable; participation is how another analysis draws on its work."
                ),
            }
        return {
            "node_id": result.node_id,
            "analysis_id": result.analysis_id,
            "recorded": result.recorded,
        }