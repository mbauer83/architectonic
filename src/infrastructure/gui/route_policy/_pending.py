"""The migration's ledger: every address 0.2.0 retires, and how far the move has got.

The manifest states the **canonical** surface. Until the last router has been visited the
served surface differs from it in exactly two ways: a retired address is still mounted, or a
canonical address is not mounted yet. Both are recorded here so the inventory fitness function
can be an *equality* — not a subset check — at every point during the migration, and so "how
much is left" is a fact in the source tree rather than a claim in a report.

:data:`RETIRED_ROUTES` is complete and constant: it is the permanent record of what 0.2.0
retires, which is what the retired-literal scan needs long after the route itself is gone. The
fitness function asserts directly that none of these addresses is served.

**The migration is over, and its scaffolding is gone.** Two collections tracked how far it had got —
which retired addresses were still mounted, and which canonical ones were not mounted yet. Both
reached the state the plan required, and a ledger that records "all of it, always" carries no
information while costing 78 lines that must be kept in lockstep with the list beside it. Six
consumers computed "the legacy addresses still served" and every one of them now reads as though the
move were still under way. What replaced them: the addressing fitness function compares the served
surface against the manifest directly, and a served address with no manifest row is a failure rather
than something the ledger explains away.

This is not a redirect table and never was — nothing here routes a request. The consumer-facing
old→new mapping lives in ``CHANGELOG.md``.
"""

from __future__ import annotations

#: Every retired ``(METHOD, template)``, and the canonical operation that replaces it.
RETIRED_ROUTES: dict[tuple[str, str], str] = {
    # ── entities ──────────────────────────────────────────────────────────────
    ("GET", "/api/entity"): "entities_read_entity",
    ("POST", "/api/entity"): "entities_create_entity",
    ("POST", "/api/entity/edit"): "entities_update_entity",
    ("POST", "/api/entity/remove"): "entities_delete_entity",
    ("GET", "/api/entity-context"): "entities_read_entity_context",
    ("GET", "/api/entity-display-item"): "diagrams_read_entity_display_item",
    ("GET", "/api/entity-schemata"): "entities_read_entity_schema",
    ("GET", "/api/neighbors"): "connections_read_entity_neighbors",
    # ── connections ───────────────────────────────────────────────────────────
    ("POST", "/api/connection"): "connections_create_connection",
    ("POST", "/api/connection/edit"): "connections_update_connection",
    ("POST", "/api/connection/remove"): "connections_delete_connection",
    ("POST", "/api/connection/associate"): "connections_update_connection_associations",
    ("POST", "/api/cleanup-broken-refs"): "connections_cleanup_broken_references",
    # ── diagrams ──────────────────────────────────────────────────────────────
    ("GET", "/api/diagram"): "diagrams_read_diagram",
    ("POST", "/api/diagram"): "diagrams_create_diagram",
    ("POST", "/api/diagram/edit"): "diagrams_replace_diagram",
    ("POST", "/api/diagram/remove"): "diagrams_delete_diagram",
    ("POST", "/api/diagram/sync"): "diagrams_sync_diagram_to_model",
    ("POST", "/api/diagram/preview"): "diagrams_preview_diagram",
    ("POST", "/api/diagram/entity-metadata"): "diagrams_update_diagram_classifier_metadata",
    ("PUT", "/api/diagram/edge-label"): "diagrams_set_diagram_edge_label",
    ("GET", "/api/diagram-connections"): "diagrams_list_diagram_connections",
    ("GET", "/api/diagram-entities"): "diagrams_list_diagram_entities",
    ("GET", "/api/diagram-context"): "diagrams_read_diagram_context",
    ("GET", "/api/diagram-download"): "diagrams_download_diagram_source",
    ("GET", "/api/diagram-svg"): "diagrams_read_diagram_svg",
    ("GET", "/api/diagram-image/{filename}"): "diagrams_read_diagram_image",
    ("GET", "/api/diagram-types/datatype/type-usages"): "diagrams_list_datatype_type_usages",
    ("GET", "/api/diagram-types/{name}/connection-types"): "diagrams_list_diagram_type_connection_types",
    ("GET", "/api/diagram-types/{name}/entity-types"): "diagrams_list_diagram_type_entity_types",
    # ── matrices ──────────────────────────────────────────────────────────────
    ("POST", "/api/matrix"): "matrices_create_matrix",
    ("POST", "/api/matrix/edit"): "matrices_replace_matrix",
    ("POST", "/api/matrix/preview"): "matrices_preview_matrix",
    ("GET", "/api/matrix-config"): "matrices_read_matrix_config",
    # ── documents ─────────────────────────────────────────────────────────────
    ("GET", "/api/document"): "documents_read_document",
    ("POST", "/api/document"): "documents_create_document",
    ("PUT", "/api/document/{artifact_id}"): "documents_update_document",
    ("DELETE", "/api/document/{artifact_id}"): "documents_delete_document",
    # ── groups ────────────────────────────────────────────────────────────────
    ("POST", "/api/group"): "groups_create_group",
    ("PUT", "/api/group"): "groups_rename_group",
    ("PATCH", "/api/group"): "groups_update_group",
    ("DELETE", "/api/group"): "groups_delete_group",
    ("POST", "/api/group/archive"): "groups_archive_group",
    ("POST", "/api/group/unarchive"): "groups_unarchive_group",
    # ── viewpoints ────────────────────────────────────────────────────────────
    ("POST", "/api/viewpoints/edit"): "viewpoints_replace_viewpoint",
    ("POST", "/api/viewpoints/remove"): "viewpoints_delete_viewpoint",
    # ── enterprise admin ──────────────────────────────────────────────────────
    ("POST", "/admin/api/entity"): "admin_create_entity",
    ("POST", "/admin/api/entity/edit"): "admin_update_entity",
    ("POST", "/admin/api/entity/remove"): "admin_delete_entity",
    ("POST", "/admin/api/connection"): "admin_create_connection",
    ("POST", "/admin/api/connection/remove"): "admin_delete_connection",
    ("POST", "/admin/api/diagram"): "admin_create_diagram",
    ("POST", "/admin/api/diagram/remove"): "admin_delete_diagram",
    # ── assurance: analysis aggregate ─────────────────────────────────────────
    ("POST", "/api/assurance/nodes"): "assurance_create_analysis_node",
    ("GET", "/api/assurance/analyses/{analysis_id}/members"): "assurance_list_participating_nodes",
    ("POST", "/api/assurance/analyses/{analysis_id}/members"): "assurance_add_participating_node",
    ("DELETE", "/api/assurance/analyses/{analysis_id}/members/{node_id}"): (
        "assurance_remove_participating_node"
    ),
    ("GET", "/api/assurance/fmea"): "assurance_read_analysis_matrix",
    ("PUT", "/api/assurance/fmea/factor"): "assurance_record_factor_assessment",
    ("GET", "/api/assurance/cast-complete"): "assurance_read_analysis_completeness",
    ("GET", "/api/assurance/grc-complete"): "assurance_read_analysis_completeness",
    ("GET", "/api/assurance/stpa-complete"): "assurance_read_analysis_completeness",
    ("GET", "/api/assurance/gsn/completeness"): "assurance_read_analysis_completeness",
    ("GET", "/api/assurance/gsn/draft"): "assurance_read_gsn_draft",
    ("GET", "/api/assurance/gsn/rendered"): "assurance_read_gsn_render",
    ("POST", "/api/assurance/gsn/publications"): "assurance_record_gsn_publication",
    ("GET", "/api/assurance/neighbors"): "assurance_read_node_neighbors",
    ("GET", "/api/assurance/guidance"): "assurance_read_guidance",
    ("POST", "/api/assurance/baselines/seal"): "assurance_seal_baseline",
    # ── assurance: architecture anchors and security signals ──────────────────
    ("GET", "/api/assurance/arch-lens/{arch_artifact_id}"): "assurance_read_arch_lens",
    ("GET", "/api/assurance/security-components"): "assurance_list_security_components",
    ("GET", "/api/assurance/security-findings"): "assurance_list_security_findings",
    ("GET", "/api/assurance/security-metrics"): "assurance_read_security_metrics",
    ("GET", "/api/assurance/vex"): "assurance_list_vex_assessments",
    ("POST", "/api/assurance/vex"): "assurance_record_vex_assessment",
    ("POST", "/api/assurance/security-ingest"): "assurance_ingest_security_signals",
    ("POST", "/api/assurance/security-snapshot-delete"): "assurance_delete_security_snapshot",
    ("GET", "/api/assurance/vulnerability-impact"): "assurance_read_vulnerability_impact",
}

#: Canonical operations the manifest declares that are not mounted yet. Either a new capability
#: the migration introduces, or the second half of a route that legacy code served as one
#: body-discriminated union.
UNSERVED_OPERATIONS: frozenset[str] = frozenset({
})
