"""REST mutation manifest: every architecture-repository mutator's authorization identity, and
the explicit classification of write-shaped operations that mutate nothing.

Handlers execute their writes exclusively through ``state.authorized_write`` /
``state.authorized_write_async``, passing their **operation id**; the helper refuses an operation
without a manifest row, so an unclassified mutator cannot execute.

Keyed by operation id, not by ``(METHOD, path)``. Four registries used to hold their own copy of a
route's path, and the copy inside each handler was the one no equality test could see: a decorator
renamed without its ``authorized_write`` tuple failed the live write closed while the suite stayed
green. An operation id is stable across a rename, so the authorization identity no longer moves when
the address does — and the route-policy manifest, which owns the address, is where a rename lands.

This remains a *second* declaration, deliberately: the route policy says an operation mutates the
repository, and this says with what intent and against which root. Two independently maintained sets
compared for equality is what makes the fitness function an oracle rather than a tautology.

Operations under ``/api/assurance`` mutate the confidential assurance store, which owns its own
unlock and capability gating — they are outside this manifest by design, and a fitness function
asserts that no repository mutator hides under that prefix.
"""

from __future__ import annotations

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationIntent,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)

ASSURANCE_ROUTE_PREFIX = "/api/assurance"

_ENGAGEMENT_OPERATIONS: tuple[str, ...] = (
    "connections_cleanup_broken_references",
    "connections_create_connection",
    "connections_delete_connection",
    "connections_update_connection",
    "connections_update_connection_associations",
    "diagrams_create_diagram",
    "diagrams_delete_diagram",
    "diagrams_replace_diagram",
    "diagrams_set_diagram_edge_label",
    "diagrams_sync_diagram_to_model",
    "diagrams_update_diagram_attribute_metadata",
    "diagrams_update_diagram_classifier_metadata",
    "documents_create_document",
    "documents_delete_document",
    "documents_update_document",
    "entities_create_entity",
    "entities_delete_entity",
    "entities_update_entity",
    "groups_archive_group",
    "groups_create_group",
    "groups_delete_group",
    "groups_rename_group",
    "groups_unarchive_group",
    "groups_update_group",
    "matrices_create_matrix",
    "matrices_replace_matrix",
    "scratchpads_create_scratchpad",
    "scratchpads_delete_scratchpad",
    "scratchpads_edit_scratchpad",
    "scratchpads_lift_scratchpad",
    "scratchpads_replace_scratchpad",
    "sync_save_engagement",
    "viewpoints_create_viewpoint",
    "viewpoints_delete_viewpoint",
    "viewpoints_replace_viewpoint",
    "viewpoints_replace_viewpoint_pins",
)

_ADMIN_OPERATIONS: tuple[str, ...] = (
    "admin_create_connection",
    "admin_create_diagram",
    "admin_create_entity",
    "admin_delete_connection",
    "admin_delete_diagram",
    "admin_delete_entity",
    "admin_update_entity",
)

_ENGAGEMENT_INTENT: MutationIntent = "engagement_authoring"
_ADMIN_INTENT: MutationIntent = "enterprise_admin_authoring"

REST_MUTATION_MANIFEST: dict[str, MutationIntent] = {
    **{operation: _ENGAGEMENT_INTENT for operation in _ENGAGEMENT_OPERATIONS},
    **{operation: _ADMIN_INTENT for operation in _ADMIN_OPERATIONS},
    "promotion_execute_promotion": "promotion",
    "sync_save_enterprise": "enterprise_save",
    "sync_submit_enterprise": "enterprise_submit",
    "sync_withdraw_enterprise": "enterprise_discard",
}

#: Write-shaped operations that mutate no repository state: previews, plans, query
#: execution/exports, and non-persistent identifier minting.
NON_MUTATING_REST_OPERATIONS: frozenset[str] = frozenset({
    "diagrams_preview_diagram",
    "entities_allocate_identifiers",
    "matrices_preview_matrix",
    "promotion_plan_promotion",
    "viewpoints_execute_viewpoint",
    "viewpoints_execute_viewpoint_diagram",
    "viewpoints_execute_viewpoint_projection",
    "viewpoints_export_viewpoint_csv",
    "viewpoints_export_viewpoint_render",
    "viewpoints_summarize_viewpoint",
})


def build_rest_request(operation_id: str) -> MutationRequest:
    """Build the MutationRequest for a manifested operation from the configured roots.

    Raises LookupError for an unmanifested operation — an unclassified mutator cannot execute a
    repository mutation, and failing here fails it closed at the request rather than in review.
    """
    from src.infrastructure.rest.routers import state as gui_state  # noqa: PLC0415

    intent = REST_MUTATION_MANIFEST.get(operation_id)
    if intent is None:
        raise LookupError(
            f"No REST mutation manifest row for operation {operation_id!r} — classify the "
            "operation before it may execute a repository mutation."
        )
    match intent:
        case "engagement_authoring" | "maintenance":
            root = gui_state.maybe_engagement_root()
            if root is None:
                raise LookupError("Engagement repository is not initialised")
            return MutationRequest(intent, RepositoryWrite(root))
        case "promotion":
            engagement, enterprise = gui_state.get_both_roots()
            return MutationRequest(intent, PromotionWrite(engagement, enterprise))
        case "enterprise_discard":
            from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

            enterprise = _enterprise_root()
            pending_remote = enterprise_sync_state.load(enterprise).is_pending()
            return MutationRequest(intent, DiscardWrite(enterprise, pending_remote=pending_remote))
        case _:
            return MutationRequest(intent, RepositoryWrite(_enterprise_root()))


def _enterprise_root():
    from src.infrastructure.rest.routers import state as gui_state  # noqa: PLC0415

    root = gui_state.maybe_enterprise_root()
    if root is None:
        raise LookupError("Enterprise repository is not configured")
    return root
