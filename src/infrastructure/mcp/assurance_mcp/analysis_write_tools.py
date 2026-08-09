"""The analysis lifecycle — the aggregate root every assurance node is created within.

Create, update and delete an analysis, plus the preflight that reads one before its findings are
promoted. Grouped here because they share the aggregate they operate on, and because the preflight
is the question an analysis is asked before its work leaves the tier it was done in.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp._write_envelopes import _analysis_result
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE, READ_ONLY


def register_analysis_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_create_analysis",
        description=(
            "Create an assurance analysis — the aggregate root for a unit of assurance work; "
            "every node is created within one analysis. method must be STPA, CAST, GRC or FMEA. "
            "An FMEA analysis holds per-component failure modes and attaches them to hazards an "
            "STPA analysis already produced, so create it alongside that analysis rather than "
            "restating its spine. "
            "architecture_anchor_id is OPTIONAL: the single system-under-analysis element when one "
            "applies (typical for STPA/CAST/FMEA); leave empty for cross-system work (typical for "
            "GRC)."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_create_analysis(
        name: str,
        method: str,
        architecture_anchor_id: str = "",
        tlp: str = "TLP:WHITE",
        status: str = "draft",
    ) -> dict[str, object]:
        from src.application.assurance import analysis as analysis_uc  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: analysis_uc.create_analysis(
            ctx.store, ctx.archive,
            name=name, method=method, architecture_anchor_id=architecture_anchor_id,
            tlp=tlp, status=status,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_update_analysis",
        description=(
            "Update an analysis's name, status (draft/active/completed/archived), or tlp. "
            "method and architecture_anchor_id are immutable (they scope the whole aggregate)."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
    )
    def assurance_update_analysis(
        analysis_id: str,
        name: str | None = None,
        status: str | None = None,
        tlp: str | None = None,
    ) -> dict[str, object]:
        from src.application.assurance import analysis as analysis_uc  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: analysis_uc.update_analysis(
            ctx.store, ctx.archive,
            analysis_id=analysis_id, name=name, status=status, tlp=tlp,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_delete_analysis",
        description=(
            "Delete an assurance analysis. Blocks (analysis_not_empty) if the analysis still owns "
            "member nodes — reassign or delete those nodes first. An empty/abandoned analysis "
            "deletes cleanly. The deletion is audited and not reversible."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
    )
    def assurance_delete_analysis(analysis_id: str) -> dict[str, object]:
        from src.application.assurance import analysis as analysis_uc  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: analysis_uc.delete_analysis(
            ctx.store, ctx.archive, analysis_id=analysis_id,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_promotion_preflight",
        description=(
            "Pre-check safety/security assurance-constraints before promoting findings to a "
            "wider audience tier. Blocks promotion if any safety/security constraint is missing "
            "a responsible-for controller OR evidence. "
            "Returns a list of blocking issues and a promote_safe flag."
        ),
        annotations=READ_ONLY,
    )
    def assurance_promotion_preflight(
        node_ids: list[str] | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.assurance.promotion import promotion_preflight  # noqa: PLC0415

        return promotion_preflight(ctx.store, node_ids=node_ids)
