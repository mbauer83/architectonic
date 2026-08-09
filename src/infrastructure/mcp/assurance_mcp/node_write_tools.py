"""The node and edge mutations — the assurance graph's own aggregate.

Split from `write_tools` for the reason `provenance_write_tools` was: that module passed the size
limit, and the split that keeps it under is by aggregate rather than by alphabet. These five tools
are the ones that change the graph itself; the baseline/reference tools and the analysis lifecycle
each own their own module beside this one.

All five delegate to `src.application.assurance.mutations`, which enforces the three-step protocol:
unlock-check → write → audit → post-write verify.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance import mutations as mutations
from src.infrastructure.assurance.edge_legality import legal_connection_types
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp._write_envelopes import _envelope
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE


def register_node_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_create_node",
        description=(
            "Create an assurance entity (loss, hazard, control-structure-node, control-action, "
            "unsafe-control-action, loss-scenario, assurance-constraint, failure-mode, evidence, "
            "risk, incident, corrective-action, obligation). "
            "For a failure-mode, set failure_type to the guideword it was enumerated against "
            "(no-function, partial-function, excessive-function, intermittent-function, "
            "unintended-function) and mode to hypothesized or observed. "
            "analysis_id is REQUIRED: it records which analysis produced the node, and it cannot "
            "be set afterwards by an ordinary edit — use assurance_assign_provenance only to "
            "repair a node that has none. "
            "Returns the new node_id. All writes are audited; post-write verification findings "
            "are included in the response (writes are never blocked by the verifier)."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_create_node(
        analysis_id: str,
        node_type: str,
        name: str,
        status: str = "draft",
        tlp: str = "TLP:WHITE",
        concern_class: str | None = None,
        disposition: str | None = None,
        uca_type: str | None = None,
        failure_type: str | None = None,
        mode: str | None = None,
        binding_status: str | None = None,
        node_role: str | None = None,
        content_text: str = "",
        attributes: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if ctx.store.get_analysis(analysis_id) is None:
            return {
                "error": "not_found",
                "analysis_id": analysis_id,
                "message": (
                    f"No analysis {analysis_id!r} exists. A node is produced by an analysis, so "
                    "one that names none cannot be created."
                ),
            }
        result = run_write(lambda: mutations.create_node(
            ctx.store, ctx.archive,
            node_type=node_type, name=name, status=status, tlp=tlp,
            concern_class=concern_class, disposition=disposition,
            uca_type=uca_type, failure_type=failure_type, mode=mode,
            binding_status=binding_status,
            node_role=node_role, analysis_id=analysis_id,
            content_text=content_text, attributes=attributes,
        ))
        return _envelope(result, ctx)

    @server.tool(
        name="assurance_add_edge",
        description=(
            "Add a typed assurance connection between two nodes. "
            "Both nodes must exist in the assurance store. "
            "The edge type must be legal for the concrete (source, target) node-type "
            "pair per the assurance ontology matrix - an illegal pair is rejected "
            "with the pair's full legal set in the error. "
            "Edge vocabulary: issues, acts-on, feedback, concerns, by-controller, "
            "leads-to, explains, derives, refines, responsible-for, accountable-for, "
            "evidenced-by, assesses, treated-by, complies-with, investigates. "
            "Cross-module architecture references (binds-to, refines-requirement, "
            "evidenced-by-artifact, purl) go through assurance_register_arch_ref, never here."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_add_edge(
        source_id: str,
        target_id: str,
        conn_type: str,
        attributes: dict[str, object] | None = None,
    ) -> dict[str, object]:
        result = run_write(lambda: mutations.add_edge(
            ctx.store, ctx.archive,
            source_id=source_id, target_id=target_id,
            conn_type=conn_type, attributes=attributes,
            legal_connection_types=legal_connection_types,
        ))
        return _envelope(result, ctx)

    @server.tool(
        name="assurance_edit_node",
        description=(
            "Update attributes of an existing assurance node. "
            "Provide only the attributes to change. "
            "Updatable: name, status, tlp, concern_class, disposition, uca_type, failure_type, mode, "
            "binding_status, "
            "node_role, content_text, attributes (dict of extra fields). "
            "analysis_id is NOT updatable: provenance is the analysis that produced the node, and "
            "it is immutable once recorded. Use assurance_assign_provenance to repair a node that "
            "has none."
        ),
        annotations=LOCAL_WRITE,
    )
    def assurance_edit_node(
        node_id: str,
        name: str | None = None,
        status: str | None = None,
        tlp: str | None = None,
        concern_class: str | None = None,
        disposition: str | None = None,
        uca_type: str | None = None,
        failure_type: str | None = None,
        mode: str | None = None,
        binding_status: str | None = None,
        node_role: str | None = None,
        content_text: str | None = None,
        attributes: dict[str, object] | None = None,
    ) -> dict[str, object]:
        result = run_write(lambda: mutations.edit_node(
            ctx.store, ctx.archive,
            node_id=node_id, name=name, status=status, tlp=tlp,
            concern_class=concern_class, disposition=disposition,
            uca_type=uca_type, failure_type=failure_type, mode=mode,
            binding_status=binding_status,
            node_role=node_role, content_text=content_text, attributes=attributes,
        ))
        return _envelope(result, ctx)

    @server.tool(
        name="assurance_delete_node",
        description=(
            "Delete an assurance node and all its incoming/outgoing edges. "
            "This action is logged in the audit trail but is not reversible."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
    )
    def assurance_delete_node(node_id: str) -> dict[str, object]:
        result = run_write(lambda: mutations.delete_node(ctx.store, ctx.archive, node_id=node_id))
        return _envelope(result, ctx)

    @server.tool(
        name="assurance_delete_edge",
        description=(
            "Delete a single assurance edge by its edge_id. "
            "Unlike assurance_delete_node, this removes only the edge (not its endpoints). "
            "The operation is logged in the audit trail and is not reversible."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
    )
    def assurance_delete_edge(edge_id: str) -> dict[str, object]:
        result = run_write(lambda: mutations.delete_edge(ctx.store, ctx.archive, edge_id=edge_id))
        return _envelope(result, ctx)
