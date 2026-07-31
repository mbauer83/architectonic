"""Operations declared ``typed`` that do not yet serve a named, closed component.

The measure of the response-contract work remaining, and nothing more than that. It used to mean
something subtly different and much less useful — "the DTO *name* in the manifest row is not the
component being served" — which made every entry an adjudication: was the handler wrong, or was the
name a Phase 0 guess about a shape nobody had modelled? Three times it was the name, and each time the
work stopped to ask. The manifest now declares a *kind* rather than a name, so an entry here says one
thing: this handler answers with an open model, an inline schema, or nothing at all, and it should
answer with a closed DTO derived from what it returns.

It shrinks per surface as each is authored, and it is **empty** when the contract is complete. Nothing
may be added: a new operation declares its DTO when it is written, which is cheap then and expensive
later.
"""

from __future__ import annotations

#: Operation ids whose declared success body is not yet the DTO the manifest names.
UNTYPED_RESPONSE_OPERATIONS: frozenset[str] = frozenset({
    "admin_read_server_info",
    "assurance_create_analysis",
    "assurance_create_edge",
    "assurance_create_group",
    "assurance_export_aibom",
    "assurance_file_analysis",
    "assurance_list_aibom_roles",
    "assurance_list_analyses",
    "assurance_list_baselines",
    "assurance_list_diagrams",
    "assurance_list_edges",
    "assurance_list_groups",
    "assurance_list_nodes",
    "assurance_list_participating_nodes",
    "assurance_model_this",
    "assurance_read_aibom_coverage",
    "assurance_read_analysis",
    "assurance_read_analysis_completeness",
    "assurance_read_analysis_matrix",
    "assurance_read_coverage",
    "assurance_read_edge_catalog",
    "assurance_read_gsn_draft",
    "assurance_read_gsn_render",
    "assurance_read_guidance",
    "assurance_read_node",
    "assurance_read_node_neighbors",
    "assurance_read_risk_register",
    "assurance_read_stats",
    "assurance_read_store_status",
    "assurance_record_factor_assessment",
    "assurance_record_gsn_publication",
    "assurance_register_arch_ref",
    "assurance_reload_store",
    "assurance_render_analysis_diagram",
    "assurance_scan_aibom_candidates",
    "assurance_seal_baseline",
    "assurance_search_nodes",
    "assurance_update_analysis",
    "assurance_verify_store",
    "connections_read_entity_neighbors",
    "connections_read_ontology",
    "connections_read_relation_notations",
    "diagrams_discover_diagram_entities",
    "diagrams_list_diagram_types",
    "diagrams_preview_diagram",
    "diagrams_read_diagram",
    "diagrams_read_diagram_context",
    "diagrams_read_diagram_type_ui_config",
    "diagrams_search_entity_display_items",
    "diagrams_sync_diagram_to_model",
    "documents_list_document_types",
    "documents_read_document_schemata",
    "documents_search_reference_artifacts",
    "entities_allocate_identifiers",
    "entities_search_artifacts",
    "entities_search_display_artifacts",
    "groups_list_groups",
    "matrices_read_matrix_config",
    "promotion_execute_promotion",
    "promotion_plan_promotion",
    "sync_read_sync_changes",
    "sync_read_sync_status",
    "taxonomy_list_modules",
    "taxonomy_read_authoring_guidance",
    "taxonomy_read_backend_identity",
    "taxonomy_read_entity_taxonomy",
    "taxonomy_read_repository_stats",
    "taxonomy_read_write_help",
    "viewpoints_execute_viewpoint",
    "viewpoints_execute_viewpoint_diagram",
    "viewpoints_execute_viewpoint_projection",
    "viewpoints_list_viewpoint_referencers",
    "viewpoints_list_viewpoints",
    "viewpoints_read_criteria_catalog",
    "viewpoints_read_diagram_viewpoint_projection",
    "viewpoints_read_viewpoint_pins",
    "viewpoints_replace_viewpoint_pins",
    "viewpoints_summarize_viewpoint",
})
