"""Assurance dashboard + assurance-case MCP tools.

Tools registered on arch-assurance-read:
  assurance_risk_register     — query view over risk entities with treatment + owner status
  assurance_coverage          — coverage/gap summary dashboard across all concerns
  assurance_draft_gsn         — scaffold GSN argument structure from store content
  assurance_case_completeness — argument-completeness check
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance.queries import coverage_gaps, risk_register
from src.infrastructure.mcp.assurance_mcp.context import ANALYSIS_SCOPE_HINT, get_assurance_context
from src.infrastructure.mcp.tool_annotations import READ_ONLY


def register_dashboard_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_risk_register",
        description=(
            "Return a tabular view of all risk entities with their treatment, owner status, "
            "linked hazards/loss-scenarios (via assesses), and treating constraints (via treated-by). "
            "Useful for the GRC risk register view (US8)."
            + ANALYSIS_SCOPE_HINT
        ),
        annotations=READ_ONLY,
    )
    def assurance_risk_register(analysis_id: str | None = None) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        nodes, edges = ctx.exposed_graph(analysis_id=analysis_id)
        return risk_register(nodes, edges)

    @server.tool(
        name="assurance_coverage",
        description=(
            "Return a coverage/gap summary across the assurance store: "
            "constraints without evidence, hazards without constraints, "
            "obligations without constraints, risks without treatment, "
            "unbound-pending CSNs, and orphan corrective-actions. "
            "Use this dashboard to identify where analysis is incomplete."
            + ANALYSIS_SCOPE_HINT
        ),
        annotations=READ_ONLY,
    )
    def assurance_coverage(analysis_id: str | None = None) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        nodes, edges = ctx.exposed_graph(analysis_id=analysis_id)
        return coverage_gaps(nodes, edges)

    @server.tool(
        name="assurance_draft_gsn",
        description=(
            "Scaffold a GSN (Goal Structuring Notation) argument structure from the assurance store. "
            "Queries losses, hazards, assurance-constraints, and evidenced-by edges to return a structured "
            "GSN dict with: top_goal (overall safety/security claim), sub_goals (one per hazard), "
            "strategies (constraint-derivation argument per hazard), solutions (evidence artifacts), "
            "and gaps (constraints without evidence, hazards without constraints)."
        ),
        annotations=READ_ONLY,
    )
    def assurance_draft_gsn(analysis_id: str | None = None) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.case_draft import draft_gsn_from_store  # noqa: PLC0415

        return draft_gsn_from_store(ctx.store, analysis_id=analysis_id)

    @server.tool(
        name="assurance_case_completeness",
        description=(
            "Run argument-completeness checks for an assurance case. "
            "Checks: every assurance-constraint has ≥1 evidenced-by edge; "
            "every hazard has ≥1 constraint via the UCA derives chain; "
            "every loss has ≥1 hazard via leads-to. "
            "Returns structured result with passed/checks/summary, same pattern as assurance_stpa_complete."
        ),
        annotations=READ_ONLY,
    )
    def assurance_case_completeness(analysis_id: str | None = None) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.case_draft import run_case_completeness  # noqa: PLC0415

        return run_case_completeness(ctx.store, analysis_id=analysis_id)
