"""REST mutation manifest: every architecture-repository REST mutator's
authorization identity, and the explicit classification of write-shaped routes
that mutate nothing.

Handlers execute their writes exclusively through ``state.authorized_write`` /
``state.authorized_write_async``, passing their route key; the helper refuses
route keys without a manifest row, so an unclassified mutator cannot execute.
Routes under ``/api/assurance`` mutate the confidential assurance store, which
owns its own unlock gating — they are outside this manifest by prefix.
"""

from __future__ import annotations

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationIntent,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)

RouteKey = tuple[str, str]

ASSURANCE_ROUTE_PREFIX = "/api/assurance"

_ENGAGEMENT_ROUTES: tuple[RouteKey, ...] = (
    ("POST", "/api/entity"),
    ("POST", "/api/entity/edit"),
    ("POST", "/api/entity/remove"),
    ("POST", "/api/connection"),
    ("POST", "/api/connection/edit"),
    ("POST", "/api/connection/associate"),
    ("POST", "/api/connection/remove"),
    ("POST", "/api/cleanup-broken-refs"),
    ("POST", "/api/document"),
    ("PUT", "/api/document/{artifact_id}"),
    ("DELETE", "/api/document/{artifact_id}"),
    ("POST", "/api/diagram"),
    ("POST", "/api/diagram/edit"),
    ("POST", "/api/diagram/entity-metadata"),
    ("POST", "/api/diagram/sync"),
    ("POST", "/api/diagram/remove"),
    ("PUT", "/api/diagram/edge-label"),
    ("POST", "/api/matrix"),
    ("POST", "/api/matrix/edit"),
    ("POST", "/api/group"),
    ("PUT", "/api/group"),
    ("PATCH", "/api/group"),
    ("DELETE", "/api/group"),
    ("POST", "/api/group/archive"),
    ("POST", "/api/group/unarchive"),
    ("PUT", "/api/viewpoints/pins"),
    ("POST", "/api/viewpoints"),
    ("POST", "/api/viewpoints/edit"),
    ("POST", "/api/viewpoints/remove"),
    ("POST", "/api/sync/engagement/save"),
)

_ADMIN_ROUTES: tuple[RouteKey, ...] = (
    ("POST", "/admin/api/entity"),
    ("POST", "/admin/api/entity/edit"),
    ("POST", "/admin/api/entity/remove"),
    ("POST", "/admin/api/connection"),
    ("POST", "/admin/api/connection/remove"),
    ("POST", "/admin/api/diagram"),
    ("POST", "/admin/api/diagram/remove"),
)

_ENGAGEMENT_INTENT: MutationIntent = "engagement_authoring"
_ADMIN_INTENT: MutationIntent = "enterprise_admin_authoring"

REST_MUTATION_MANIFEST: dict[RouteKey, MutationIntent] = {
    **{route: _ENGAGEMENT_INTENT for route in _ENGAGEMENT_ROUTES},
    **{route: _ADMIN_INTENT for route in _ADMIN_ROUTES},
    ("POST", "/api/promote/execute"): "promotion",
    ("POST", "/api/sync/enterprise/save"): "enterprise_save",
    ("POST", "/api/sync/enterprise/submit"): "enterprise_submit",
    ("POST", "/api/sync/enterprise/withdraw"): "enterprise_discard",
}

# Write-shaped routes that mutate no repository state: previews, plans, query
# execution/exports, and non-persistent identifier minting.
NON_MUTATING_REST_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("POST", "/api/diagram/preview"),
        ("POST", "/api/matrix/preview"),
        ("POST", "/api/promote/plan"),
        ("POST", "/api/viewpoints/summarize"),
        ("POST", "/api/viewpoints/execute"),
        ("POST", "/api/viewpoints/export-csv"),
        ("POST", "/api/viewpoints/export-render"),
        ("POST", "/api/viewpoints/execute-projection"),
        ("POST", "/api/viewpoints/execute-diagram"),
        ("POST", "/api/identifiers/allocate"),
    }
)


def build_rest_request(route: RouteKey) -> MutationRequest:
    """Build the MutationRequest for a manifested route from the configured roots.

    Raises LookupError for unmanifested routes — an unclassified mutator cannot
    execute a write.
    """
    from src.infrastructure.gui.routers import state as gui_state  # noqa: PLC0415

    intent = REST_MUTATION_MANIFEST.get(route)
    if intent is None:
        raise LookupError(
            f"No REST mutation manifest row for route {route!r} — classify the route "
            "before it may execute a repository mutation."
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
    from src.infrastructure.gui.routers import state as gui_state  # noqa: PLC0415

    root = gui_state.maybe_enterprise_root()
    if root is None:
        raise LookupError("Enterprise repository is not configured")
    return root
