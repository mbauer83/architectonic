"""Assurance filing and participation MCP tools.

Tools registered on arch-assurance-write:
  assurance_create_group           — create a group that files analyses
  assurance_delete_group           — delete a group; its analyses survive, unfiled
  assurance_file_analysis          — file an analysis into a group, or unfile it
  assurance_add_analysis_member    — draw a node into an analysis that did not author it
  assurance_remove_analysis_member — stop a node participating

Its own module for the reason the factor-judgement tools have one: three relations that answer
different questions do not belong in one file with node and edge CRUD, and `write_tools` was at the
source-length limit.

**Why these exist as tools at all.** Authoring goes through tools, so a capability with no tool is a
capability an analyst cannot use. Filing and participation were reachable only over REST until now,
which is also why 26 nodes in the live store have no author recorded: the write surface could not
say so.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application import assurance_grouping as grouping_uc
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp._write_envelopes import _analysis_result
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context


def register_grouping_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()


    @server.tool(
        name="assurance_create_group",
        description=(
            "Create a group that files assurance analyses. A group has no method of its own — "
            "that is what distinguishes it from the analyses it holds. Deleting a group never "
            "deletes its analyses."
        ),
    )
    def assurance_create_group(name: str, description: str = "") -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: grouping_uc.create_group(
            ctx.store, ctx.archive, name=name, description=description,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_delete_group",
        description=(
            "Delete a group. Its analyses survive, unfiled: filing and content are the same "
            "gesture in a UI and must never be the same gesture in the store."
        ),
    )
    def assurance_delete_group(group_id: str) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: grouping_uc.delete_group(
            ctx.store, ctx.archive, group_id=group_id,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_file_analysis",
        description=(
            "File an analysis into a group, or pass group_id=null to unfile it. An analysis is "
            "worth recording before anyone settles where it belongs, so unfiling is a normal "
            "operation rather than an error."
        ),
    )
    def assurance_file_analysis(
        analysis_id: str,
        group_id: str | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: grouping_uc.file_analysis(
            ctx.store, ctx.archive, analysis_id=analysis_id, group_id=group_id,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_add_analysis_member",
        description=(
            "Draw an existing node into an analysis that did not author it, so one method can "
            "reason over another's work without copying it — an FMEA enumerating failure modes "
            "against the control-structure nodes an STPA identified. Authorship is untouched and "
            "no copy is made. Idempotent."
        ),
    )
    def assurance_add_analysis_member(analysis_id: str, node_id: str) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: grouping_uc.add_participant(
            ctx.store, ctx.archive, analysis_id=analysis_id, node_id=node_id,
        ))
        return _analysis_result(result, ctx)

    @server.tool(
        name="assurance_remove_analysis_member",
        description=(
            "Stop a node participating in an analysis. The node survives, still owned by the "
            "analysis that authored it."
        ),
    )
    def assurance_remove_analysis_member(analysis_id: str, node_id: str) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        result = run_write(lambda: grouping_uc.remove_participant(
            ctx.store, ctx.archive, analysis_id=analysis_id, node_id=node_id,
        ))
        return _analysis_result(result, ctx)
