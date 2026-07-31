"""Canonical route policy for the git-sync, promotion and enterprise-admin surfaces.

These operations address no repository artifact: they move work between two repositories or
report on the working tree. Their bodies are command operands, so they keep action segments —
and every one of them touches git, which is why none is cacheable and all are
``derived-graph``: a fetch or a push is bounded by the network, not by the index.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._types import RouteRow

_ARTIFACT = ("artifact_id",)

SYNC_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/sync/status", "catalog", "sync_read_sync_status", "SyncStatusResponse"),
    RouteRow(
        "GET", "/api/sync/changes", "catalog", "sync_read_sync_changes", "SyncChangeListResponse",
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/engagement/save", "operation", "sync_save_engagement",
        "EngagementSaveResponse",
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/save", "operation", "sync_save_enterprise",
        "EnterpriseSaveResponse",
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/submit", "operation", "sync_submit_enterprise",
        "EnterpriseSubmitResponse", mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/sync/enterprise/withdraw", "operation", "sync_withdraw_enterprise",
        "EnterpriseWithdrawResponse", mutation_domain="repository", timeout_class="derived-graph",
    ),
)

PROMOTION_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "POST", "/api/promote/plan", "operation", "promotion_plan_promotion", "PromotionPlanResponse",
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/promote/execute", "operation", "promotion_execute_promotion",
        "PromotionExecutionResponse", mutation_domain="repository", timeout_class="derived-graph",
    ),
)

ADMIN_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/admin/api/server-info", "catalog", "admin_read_server_info", "AdminServerInfoResponse",
        cache_directive="private",
    ),
    RouteRow(
        "POST", "/admin/api/entities", "collection", "admin_create_entity", "WriteResultResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/admin/api/entities/{artifact_id}", "detail", "admin_update_entity",
        "WriteResultResponse", identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/admin/api/entities/{artifact_id}", "detail", "admin_delete_entity",
        "WriteResultResponse", identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/admin/api/connections", "collection", "admin_create_connection", "WriteResultResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/admin/api/connections/{connection_id}", "detail", "admin_delete_connection",
        "WriteResultResponse", identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/admin/api/diagrams", "collection", "admin_create_diagram", "WriteResultResponse",
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "DELETE", "/admin/api/diagrams/{artifact_id}", "detail", "admin_delete_diagram",
        "WriteResultResponse", identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
)
