"""Canonical route policy for the git-sync, promotion and enterprise-admin surfaces.

These operations address no repository artifact: they move work between two repositories or
report on the working tree. Their bodies are command operands, so they keep action segments —
and every one of them touches git, which is why none is cacheable and all are
``derived-graph``: a fetch or a push is bounded by the network, not by the index.
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import TYPED, RouteRow

_ARTIFACT = ("artifact_id",)

SYNC_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/sync/status", "catalog", "sync_read_sync_status", TYPED),
    RouteRow(
        "GET", "/api/sync/changes", "catalog", "sync_read_sync_changes", TYPED,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/engagement/save", "operation", "sync_save_engagement",
        TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/save", "operation", "sync_save_enterprise",
        TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/submit", "operation", "sync_submit_enterprise",
        TYPED, mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/withdraw", "operation", "sync_withdraw_enterprise",
        TYPED, mutation_domain="repository", timeout_class="derived-graph",
    ),
)

PROMOTION_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "POST", "/api/promote/plan", "operation", "promotion_plan_promotion", TYPED,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/promote/execute", "operation", "promotion_execute_promotion",
        TYPED, mutation_domain="repository", timeout_class="derived-graph",
    ),
)

ADMIN_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/admin/api/server-info", "catalog", "admin_read_server_info", TYPED,
        cache_directive="private",
    ),
    RouteRow(
        "POST", "/admin/api/entities", "collection", "admin_create_entity", TYPED,
        mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/admin/api/entities/{artifact_id}", "detail", "admin_update_entity",
        TYPED, identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/admin/api/entities/{artifact_id}", "detail", "admin_delete_entity",
        TYPED, identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/admin/api/connections", "collection", "admin_create_connection", TYPED,
        mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/admin/api/connections/{connection_id}", "detail", "admin_delete_connection",
        TYPED, identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/admin/api/diagrams", "collection", "admin_create_diagram", TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "DELETE", "/admin/api/diagrams/{artifact_id}", "detail", "admin_delete_diagram",
        TYPED, identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
)
