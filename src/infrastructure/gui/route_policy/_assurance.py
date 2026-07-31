"""Canonical route policy for the confidential assurance surface.

Three relations, three addresses. **Filing** is a group→analysis link, so it is a singleton
subresource of the analysis (``/group``). **Provenance** is the analysis that authored a node,
single-valued and immutable once set, so it is a singleton subresource of the *node*
(``/provenance``) and that is the only route permitted to set it. **Participation** is
many-to-many and directional — a node participates in an analysis, never the reverse — so it
is a member of the analysis's ``participating-nodes`` collection.

FMEA is a ``method`` of analysis rather than a child resource, so there is one canonical
analysis collection and the method-specific projections (``/matrix``, ``/completeness``) hang
off an identified analysis. A projection asked of the wrong method is a typed 409, not an
empty result.

Every response on this surface carries ``no-store`` — success and error alike — and none is
eligible for conditional reads: a direct read of an above-ceiling id must stay
indistinguishable from a read of an absent one, and an ETag would leak the difference.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._types import BODYLESS, TYPED, RouteRow

_ANALYSIS = ("analysis_id",)
_NODE = ("node_id",)
_ARCH = ("arch_artifact_id",)
_PARTICIPATION = ("analysis_id", "node_id")

ANALYSIS_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/assurance/analyses", "collection", "assurance_list_analyses", TYPED),
    RouteRow(
        "POST", "/api/assurance/analyses", "collection", "assurance_create_analysis",
        TYPED, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}", "detail", "assurance_read_analysis",
        TYPED, identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "PATCH", "/api/assurance/analyses/{analysis_id}", "detail", "assurance_update_analysis",
        TYPED, identity_parameters=_ANALYSIS, mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/analyses/{analysis_id}", "detail", "assurance_delete_analysis",
        BODYLESS, identity_parameters=_ANALYSIS, mutation_domain="assurance",
    ),
    RouteRow(
        "PUT", "/api/assurance/analyses/{analysis_id}/group", "subresource", "assurance_file_analysis",
        TYPED, identity_parameters=_ANALYSIS, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/nodes", "subresource",
        "assurance_list_analysis_nodes", TYPED, identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "POST", "/api/assurance/analyses/{analysis_id}/nodes", "subresource",
        "assurance_create_analysis_node", TYPED,
        identity_parameters=_ANALYSIS, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/participating-nodes", "subresource",
        "assurance_list_participating_nodes", TYPED,
        identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "PUT", "/api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}", "subresource",
        "assurance_add_participating_node", BODYLESS,
        identity_parameters=_PARTICIPATION, mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}", "subresource",
        "assurance_remove_participating_node", BODYLESS,
        identity_parameters=_PARTICIPATION, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/matrix", "subresource",
        "assurance_read_analysis_matrix", TYPED, identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/completeness", "subresource",
        "assurance_read_analysis_completeness", TYPED,
        identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/gsn/publications", "subresource",
        "assurance_list_gsn_publications", TYPED, identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "POST", "/api/assurance/analyses/{analysis_id}/gsn/publications", "subresource",
        "assurance_record_gsn_publication", TYPED,
        identity_parameters=_ANALYSIS, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/gsn/draft", "subresource",
        "assurance_read_gsn_draft", TYPED, identity_parameters=_ANALYSIS,
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/gsn/rendered", "subresource",
        "assurance_read_gsn_render", TYPED,
        identity_parameters=_ANALYSIS, timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/assurance/analyses/{analysis_id}/diagrams/{diagram_type}/rendered", "subresource",
        "assurance_render_analysis_diagram", TYPED,
        identity_parameters=("analysis_id", "diagram_type"), timeout_class="derived-graph",
    ),
)

NODE_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/assurance/nodes", "collection", "assurance_list_nodes", TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/nodes/{node_id}", "detail", "assurance_read_node",
        TYPED, identity_parameters=_NODE,
    ),
    RouteRow(
        "PATCH", "/api/assurance/nodes/{node_id}", "detail", "assurance_update_node",
        TYPED, identity_parameters=_NODE, mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/nodes/{node_id}", "detail", "assurance_delete_node", BODYLESS,
        identity_parameters=_NODE, mutation_domain="assurance",
    ),
    RouteRow(
        # 204 in every accepted case. The relation either holds or it does not, so re-asserting it
        # must be indistinguishable from asserting it once — there is no outcome left to report,
        # and a body saying "already set" would be a second state a caller has to handle.
        "PUT", "/api/assurance/nodes/{node_id}/provenance", "subresource",
        "assurance_assign_node_provenance", BODYLESS,
        identity_parameters=_NODE, mutation_domain="assurance",
    ),
    RouteRow(
        "POST", "/api/assurance/nodes/{node_id}/factor-assessments", "subresource",
        "assurance_record_factor_assessment", TYPED,
        identity_parameters=_NODE, mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/nodes/{node_id}/neighbors", "subresource",
        "assurance_read_node_neighbors", TYPED,
        identity_parameters=_NODE, timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/assurance/edges", "collection", "assurance_list_edges", TYPED,
    ),
    RouteRow(
        "POST", "/api/assurance/edges", "collection", "assurance_create_edge", TYPED,
        mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/edges/{edge_id}", "detail", "assurance_delete_edge", BODYLESS,
        identity_parameters=("edge_id",), mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/edge-catalog", "catalog", "assurance_read_edge_catalog",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/groups", "collection", "assurance_list_groups",
        TYPED,
    ),
    RouteRow(
        "POST", "/api/assurance/groups", "collection", "assurance_create_group",
        TYPED, mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/groups/{group_id}", "detail", "assurance_delete_group", BODYLESS,
        identity_parameters=("group_id",), mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/search", "collection", "assurance_search_nodes",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/guidance/{topic}", "detail", "assurance_read_guidance",
        TYPED, identity_parameters=("topic",),
    ),
    RouteRow(
        "GET", "/api/assurance/diagrams", "collection", "assurance_list_diagrams",
        TYPED,
    ),
)

STORE_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/assurance/status", "catalog", "assurance_read_store_status", TYPED),
    RouteRow("GET", "/api/assurance/stats", "catalog", "assurance_read_stats", TYPED),
    RouteRow("GET", "/api/assurance/coverage", "catalog", "assurance_read_coverage", TYPED),
    RouteRow("GET", "/api/assurance/risk-register", "catalog", "assurance_read_risk_register", TYPED),
    RouteRow(
        "GET", "/api/assurance/verify", "catalog", "assurance_verify_store", TYPED,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/assurance/baselines", "collection", "assurance_list_baselines", TYPED,
    ),
    RouteRow(
        "POST", "/api/assurance/baselines", "collection", "assurance_seal_baseline", TYPED,
        mutation_domain="assurance", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/assurance/arch-refs", "collection", "assurance_register_arch_ref",
        TYPED, mutation_domain="assurance",
    ),
    RouteRow(
        "POST", "/api/assurance/reload", "operation", "assurance_reload_store", TYPED,
        mutation_domain="assurance",
    ),
    RouteRow(
        "POST", "/api/assurance/model-this", "operation", "assurance_model_this",
        TYPED, mutation_domain="assurance",
    ),
)

SIGNAL_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/assurance/arch-artifacts/{arch_artifact_id}/lens", "subresource",
        "assurance_read_arch_lens", TYPED, identity_parameters=_ARCH,
    ),
    RouteRow(
        "GET", "/api/assurance/arch-artifacts/{arch_artifact_id}/security-components", "subresource",
        "assurance_list_security_components", TYPED, identity_parameters=_ARCH,
    ),
    RouteRow(
        # Addressed by the internal ``SCM@…`` id, never by a PURL or a ``bom_ref``. Those are the
        # source's identifiers: their grammar carries structure a path segment cannot, and one
        # package appears under different ones across feeds. They stay on the row, and as filters.
        "GET", "/api/assurance/security-components/{component_id}", "detail",
        "assurance_read_security_component", TYPED,
        identity_parameters=("component_id",),
    ),
    RouteRow(
        "GET", "/api/assurance/arch-artifacts/{arch_artifact_id}/security-findings", "subresource",
        "assurance_list_security_findings", TYPED, identity_parameters=_ARCH,
    ),
    RouteRow(
        "GET", "/api/assurance/arch-artifacts/{arch_artifact_id}/security-metrics", "subresource",
        "assurance_read_security_metrics", TYPED, identity_parameters=_ARCH,
    ),
    RouteRow(
        "GET", "/api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments", "subresource",
        "assurance_list_vex_assessments", TYPED, identity_parameters=_ARCH,
    ),
    RouteRow(
        "POST", "/api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments", "subresource",
        "assurance_record_vex_assessment", TYPED,
        identity_parameters=_ARCH, mutation_domain="assurance",
    ),
    RouteRow(
        "POST", "/api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots", "subresource",
        "assurance_ingest_security_signals", TYPED,
        identity_parameters=_ARCH, mutation_domain="assurance", timeout_class="derived-graph",
    ),
    RouteRow(
        "DELETE", "/api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots", "subresource",
        "assurance_delete_anchor_security_snapshots", TYPED,
        identity_parameters=_ARCH, mutation_domain="assurance",
    ),
    RouteRow(
        "DELETE", "/api/assurance/security-snapshots/{snapshot_id}", "detail",
        "assurance_delete_security_snapshot", TYPED,
        identity_parameters=("snapshot_id",), mutation_domain="assurance",
    ),
    RouteRow(
        "GET", "/api/assurance/security-stats", "catalog", "assurance_read_security_stats",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/signal-anchor-types", "catalog", "assurance_list_signal_anchor_types",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/vulnerabilities/{identifier}/impact", "subresource",
        "assurance_read_vulnerability_impact", TYPED,
        identity_parameters=("identifier",),
    ),
    RouteRow(
        "GET", "/api/assurance/aibom/coverage", "catalog", "assurance_read_aibom_coverage",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/aibom/roles", "catalog", "assurance_list_aibom_roles",
        TYPED,
    ),
    RouteRow(
        "GET", "/api/assurance/aibom/scan", "collection", "assurance_scan_aibom_candidates",
        TYPED, timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/assurance/aibom/export", "operation", "assurance_export_aibom",
        TYPED, timeout_class="derived-graph",
    ),
)
