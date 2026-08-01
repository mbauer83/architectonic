"""Assurance read-only MCP tools (core).

Tools registered on arch-assurance-read:
  assurance_store_status  — store config/lock status (gating check; always callable)
  assurance_list_nodes    — list assurance entities with filters
  assurance_read_node     — read a single assurance entity (+ factor report for a failure mode)
  assurance_fmea_matrix   — the failure-mode matrix (registered in fmea_read_tools.py)
  assurance_list_edges    — list connections in/out of a node
  assurance_stats         — counts by type
  assurance_verify        — run the structural validity rules
  assurance_guidance      — per-step STPA/CAST/GRC method guidance
  assurance_stpa_complete — STPA coverage profile check
  assurance_cast_complete — CAST coverage profile check
  assurance_grc_complete  — GRC control-coverage-complete check

Dashboard/case tools are in dashboard_tools.py (registered via register_dashboard_tools).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.assurance.node_sorting import MOST_RECENTLY_UPDATED_FIRST
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.mcp.assurance_mcp.context import (
    _exposure_log,
    get_assurance_context,
)
from src.infrastructure.mcp.assurance_mcp.dashboard_tools import register_dashboard_tools
from src.infrastructure.mcp.assurance_mcp.fmea_read_tools import register_fmea_read_tools
from src.infrastructure.mcp.assurance_mcp.security_read_tools import register_security_read_tools

FAILURE_MODE_NODE_TYPE = "failure-mode"


def register_read_tools(server: FastMCP) -> None:
    register_security_read_tools(server)
    register_dashboard_tools(server)
    register_fmea_read_tools(server)
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_store_status",
        description=(
            "Return the current status of the confidential assurance store: whether it is "
            "configured, locked, or unlocked. Always callable — does not require the store to be open."
        ),
    )
    def assurance_store_status() -> dict[str, object]:
        from src.infrastructure.mcp.assurance_mcp.context import default_db_path  # noqa: PLC0415

        bundle = ctx._bundle()  # noqa: SLF001
        store = bundle.store
        unlocked = store.is_unlocked()
        db_path = default_db_path()
        return {
            "store_backend": bundle.store_backend,
            "signals_backend": bundle.signals_backend,
            "max_classification": ctx.max_classification,
            "db_path": str(db_path),
            "db_exists": db_path.exists(),
            "unlocked": unlocked,
            "status": "unlocked" if unlocked else ("locked" if db_path.exists() else "not_initialised"),
            "hint": (
                None
                if unlocked
                else (
                    "Run `arch-assurance unlock` to open the store."
                    if db_path.exists()
                    else "Run `arch-assurance init` to initialise the store."
                )
            ),
        }

    @server.tool(
        name="assurance_list_nodes",
        description=(
            "List assurance entities (losses, hazards, UCAs, constraints, etc.). "
            "Filter by node_type, status, concern_class, or tlp. "
            "sort: updated_at (default) | created_at | name | node_type; order: desc (default) | asc."
        ),
    )
    def assurance_list_nodes(
        node_type: str | None = None,
        status: str | None = None,
        concern_class: str | None = None,
        tlp: str | None = None,
        sort: str = MOST_RECENTLY_UPDATED_FIRST[0],
        order: str = MOST_RECENTLY_UPDATED_FIRST[1],
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        policy = AssuranceExposurePolicy(ctx.max_classification, True)
        # Ordered in the store, ahead of the exposure filter: filtering is order-preserving,
        # so sorting cannot change which nodes are exposed nor leak the withheld count.
        nodes = ctx.store.list_nodes(
            node_type=node_type,
            status=status,
            concern_class=concern_class,
            tlp=tlp,
            sort=sort,
            order=order,
        )
        exposed, withheld_count = policy.filter_nodes(nodes)
        if withheld_count:
            _exposure_log.info(
                "list_nodes: ceiling=%s returned=%d withheld=%d",
                ctx.max_classification, len(exposed), withheld_count,
            )
        return {"nodes": exposed, "count": len(exposed), "withheld": withheld_count}

    @server.tool(
        name="assurance_read_node",
        description=(
            "Read a single assurance entity by node_id. Returns all attributes and content. "
            "For a failure-mode it also returns factor_report: each factor's effective value, "
            "whether it is derived or asserted, and the basis_digest that a judgement must be "
            "recorded against — pass that digest to assurance_set_fmea_factor, which is the only "
            "way an assertion applies. Plus the action priority, whether an occurrence is being "
            "asked for at all, and the single next action that would advance the row."
        ),
    )
    def assurance_read_node(node_id: str) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        policy = AssuranceExposurePolicy(ctx.max_classification, True)
        node = ctx.store.get_node(node_id)
        from src.application.assurance.exposure import Visible  # noqa: PLC0415
        outcome = policy.apply_node(node)
        if not isinstance(outcome, Visible):
            return ctx.not_found_response(node_id)
        edges_out = ctx.store.list_edges(source_id=node_id)
        edges_in = ctx.store.list_edges(target_id=node_id)
        payload: dict[str, object] = {
            "node": outcome.value,
            "outgoing_edges": edges_out,
            "incoming_edges": edges_in,
        }
        # A failure mode's factors are its content, and the digest is only obtainable here: an
        # agent working through MCP has no other read of the matrix, so without this the write
        # tool cannot be used at all.
        if str(dict(outcome.value).get("node_type") or "") == FAILURE_MODE_NODE_TYPE:
            from src.application.assurance.fmea_lens import factor_report  # noqa: PLC0415
            from src.infrastructure.assurance.architecture_basis import (  # noqa: PLC0415
                current_architecture_basis,
            )

            visible, _ = policy.filter_nodes(ctx.store.list_nodes())
            payload["factor_report"] = factor_report(
                node_id, store=ctx.store, policy=policy, nodes=visible,
                basis=current_architecture_basis(),
            )
        return payload

    @server.tool(
        name="assurance_list_edges",
        description=(
            "List assurance connections. Filter by source_id, target_id, or conn_type."
        ),
    )
    def assurance_list_edges(
        source_id: str | None = None,
        target_id: str | None = None,
        conn_type: str | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        edges = ctx.store.list_edges(source_id=source_id, target_id=target_id, conn_type=conn_type)
        return {"edges": edges, "count": len(edges)}

    @server.tool(
        name="assurance_stats",
        description="Return counts of assurance nodes and edges by type.",
    )
    def assurance_stats() -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        policy = AssuranceExposurePolicy(ctx.max_classification, True)
        visible, _ = policy.filter_nodes(ctx.store.list_nodes())
        return policy.redact_stats(visible, ctx.store.list_edges())

    @server.tool(
        name="assurance_verify",
        description=(
            "Run the hard structural validity checks on all assurance entities in the store. "
            "Returns errors (block sign-off) and warnings (informational). "
            "Also emits W501 modeling-gap findings for unbound-pending control-structure-nodes."
        ),
    )
    def assurance_verify() -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.assurance_verifier import format_result, verify_store  # noqa: PLC0415
        from src.infrastructure.assurance.arch_ref_resolver import dangling_arch_refs  # noqa: PLC0415
        from src.infrastructure.assurance.architecture_basis import shared_artifact_lookup  # noqa: PLC0415

        result = verify_store(ctx.store, basis=current_architecture_basis())
        payload = format_result(result)
        # An assurance node citing an architecture artifact that no longer exists is a
        # modelling gap, and this is the read that surfaces gaps. Reported separately from
        # the store's own findings because it is a statement about the *pair* of models,
        # and it is informational: the architecture is allowed to move on.
        lookup = shared_artifact_lookup()
        if lookup is not None:
            payload["architecture_references"] = dangling_arch_refs(ctx.store, lookup)
        return payload

    @server.tool(
        name="assurance_stpa_complete",
        description=(
            "Run the stpa-basic-complete coverage profile check on the assurance store. "
            "Checks: every hazard has ≥1 leads-to loss; every UCA has ≥1 concerns control-action "
            "AND ≥1 leads-to hazard; every loss-scenario explains ≥1 UCA or ≥1 hazard; every UCA and "
            "loss-scenario has ≥1 derives constraint. Returns gap counts and node IDs for each check."
        ),
    )
    def assurance_stpa_complete() -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.stpa_complete import run_stpa_complete  # noqa: PLC0415

        return run_stpa_complete(ctx.store)

    @server.tool(
        name="assurance_guidance",
        description=(
            "Return per-step STPA/CAST/GRC method guidance: what the step means, why it matters, "
            "and which standard applies. Always callable — does not require the store to be open. "
            "Topic examples: 'stpa-losses', 'stpa-hazards', 'stpa-control-structure', "
            "'stpa-ucas', 'stpa-constraints', 'grc-risk', 'grc-obligations', 'cast-investigation'."
        ),
    )
    def assurance_guidance(topic: str) -> dict[str, object]:
        from src.application.assurance.guidance import lookup  # noqa: PLC0415

        return lookup(topic)

    @server.tool(
        name="assurance_cast_complete",
        description=(
            "Run the cast-complete coverage profile check. "
            "Fails if any incident exists without a sealed analysis_baseline. "
            "Also checks: every incident has ≥1 investigates edge; every corrective-action "
            "has ≥1 derives edge to a constraint. Returns gap counts per check."
        ),
    )
    def assurance_cast_complete() -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.cast_complete import run_cast_complete  # noqa: PLC0415

        return run_cast_complete(ctx.store, ctx.archive)

    @server.tool(
        name="assurance_grc_complete",
        description=(
            "Run the grc-control-coverage-complete profile check. "
            "Checks: every obligation has ≥1 complies-with constraint; "
            "every risk has a treatment attribute; every risk has an accountable-for owner. "
            "Returns gap counts per check."
        ),
    )
    def assurance_grc_complete() -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        from src.application.verification.grc_complete import run_grc_complete  # noqa: PLC0415

        return run_grc_complete(ctx.store)

    @server.tool(
        name="assurance_list_analyses",
        description=(
            "List assurance analyses — the aggregate roots for units of STPA/CAST/GRC work. "
            "Filter by method (STPA/CAST/GRC) or status. Pass analysis_id to fetch one analysis. "
            "Above-ceiling analyses are omitted; an absent or above-ceiling id returns not_found."
        ),
    )
    def assurance_list_analyses(
        method: str | None = None,
        status: str | None = None,
        analysis_id: str | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        policy = AssuranceExposurePolicy(ctx.max_classification, True)
        if analysis_id:
            from src.application.assurance.exposure import Visible  # noqa: PLC0415

            outcome = policy.apply_analysis(ctx.store.get_analysis(analysis_id))
            if isinstance(outcome, Visible):
                return {"analysis": outcome.value}
            return ctx.not_found_response(analysis_id)
        exposed, _ = policy.filter_analyses(ctx.store.list_analyses(method=method, status=status))
        return {"analyses": exposed, "count": len(exposed)}
