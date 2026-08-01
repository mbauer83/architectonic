"""Every address 0.2.0 retires, and the canonical operation that replaced it.

A permanent record, complete and constant. What needs it is the retired-literal scan, which fails a
reference to any of these addresses anywhere in the tree — long after the route itself is gone — and
the CHANGELOG cross-check, which holds the consumer-facing old→new mapping against this one.

The module was called ``_pending`` and carried two collections tracking how far the migration had
got: which retired addresses were still mounted, and which canonical ones were not mounted yet. Both
reached empty, and an allowlist that must stay empty is not a fact — it is a conditional in every
consumer, each reading as though the move were still under way. What replaced them is stronger: the
addressing fitness function compares the served surface against the manifest as a plain equality, so
a served address with no manifest row fails rather than being explained away.

This is not a redirect table and never was — nothing here routes a request.
"""

from __future__ import annotations

#: Every retired ``(METHOD, template)``, and the canonical operation that replaces it.
RETIRED_ROUTES: dict[tuple[str, str], str] = {
    # One address answered two questions, choosing its shape by whether `target_type` was supplied, and
    # answered an invalid endpoint with a 200 carrying an error string. Split, because the two shapes are
    # two operations — the GUI had already modelled them as two calls with two decoders.
    ("GET", "/api/ontology"): "connections_read_ontology_classification",
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
