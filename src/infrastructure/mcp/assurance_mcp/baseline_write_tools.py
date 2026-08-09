"""Sealing a baseline, recording an architecture reference, and proposing a binding.

The three tools that reach outside the assurance graph without leaving the store: a baseline pins
what the graph said at a moment, a reference names an architecture artifact, and `model_this`
describes the architecture entity somebody else must create. Grouped here because the one-way
persistence rule is what they have in common — none of them writes to the architecture repository,
and `model_this` returns a task spec precisely so that separation of duties survives.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance import mutations as mutations
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp._write_envelopes import _envelope
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.tool_annotations import LOCAL_WRITE, READ_ONLY


def register_baseline_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_seal_baseline",
        description=(
            "Seal a signed baseline of the current assurance analysis state. "
            "The baseline captures the current audit-log head hash as a tamper-evident snapshot. "
            "Required before CAST investigations (pins the 'as-existed' model state). "
            "Also satisfies EU AI Act Art. 18 technical-documentation retention."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_seal_baseline(
        notes: str = "",
        analysis_id: str | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        return run_write(lambda: ctx.archive.seal_baseline(notes=notes, analysis_id=analysis_id))

    @server.tool(
        name="assurance_register_arch_ref",
        description=(
            "Record an assurance→architecture cross-reference. "
            "This is the ONLY direction allowed (one-way persistence rule). "
            "The architecture artifact ID must be a valid ID from the arch-repo-read store. "
            "Dangling refs (arch entity not found) are tolerated and marked as unresolved."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_register_arch_ref(
        assurance_node_id: str,
        arch_artifact_id: str,
        ref_type: str,
    ) -> dict[str, object]:
        result = run_write(lambda: mutations.register_arch_ref(
            ctx.store, ctx.archive,
            assurance_node_id=assurance_node_id,
            arch_artifact_id=arch_artifact_id,
            ref_type=ref_type,
        ))
        return _envelope(result, ctx)

    @server.tool(
        name="assurance_model_this",
        description=(
            "Propose an architecture entity to bind an unbound-pending control-structure-node. "
            "Returns a structured three-step task spec telling the agent what to call on "
            "arch-repo-write to create the architecture entity, then register the arch reference, "
            "then update binding_status to 'bound'. This assurance-scoped server does NOT modify "
            "the architecture repository — the GUI's create+bind path (POST /api/assurance/model-this) "
            "is the direct-bind alternative."
        ),
        annotations=READ_ONLY,
    )
    def assurance_model_this(
        assurance_node_id: str,
        suggested_arch_type: str,
        suggested_name: str,
        domain: str = "application",
    ) -> dict[str, object]:
        from src.application.assurance import model_bind as model_bind  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        # No architecture-write port here (separation of duties): always a task spec.
        result = run_write(lambda: model_bind.model_and_bind(
            ctx.store, ctx.archive,
            assurance_node_id=assurance_node_id,
            suggested_arch_type=suggested_arch_type,
            suggested_name=suggested_name,
            domain=domain,
            arch_creator=None,
        ))
        if isinstance(result, model_bind.BindNotFound):
            return ctx.not_found_response(result.assurance_node_id)
        if isinstance(result, model_bind.BindLocked):
            return ctx.locked_response()
        if isinstance(result, model_bind.BindInvalid):
            return {
                "error": result.error,
                "assurance_node_id": assurance_node_id,
                "message": result.message,
            }
        if isinstance(result, model_bind.TaskRequired):
            return result.spec
        return {  # defensive: Bound never occurs with arch_creator=None
            "outcome": "bound",
            "assurance_node_id": result.assurance_node_id,
            "arch_artifact_id": result.arch_artifact_id,
        }
