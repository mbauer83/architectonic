"""Canonical route policy for the icon library.

An icon is addressed by its artifact id; what it applies to, its tag and its name narrow the
collection rather than naming a resource (ADR@1785451831). The picture is a subresource served as
bytes: an icon's picture never changes under its id — replacing a logo is a new icon — so a browser
may keep it, privately, for as long as it likes.
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import BODYLESS, MEDIA, TYPED, RouteRow

_ID = ("artifact_id",)

ICON_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/icons", "collection", "icons_list_icons", TYPED, cache_directive="no-cache"),
    RouteRow("POST", "/api/icons", "collection", "icons_create_icon", TYPED, mutation_domain="repository"),
    RouteRow(
        "GET", "/api/icons/{artifact_id}", "detail", "icons_read_icon", TYPED,
        identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "PATCH", "/api/icons/{artifact_id}", "detail", "icons_update_icon", TYPED,
        identity_parameters=_ID, mutation_domain="repository",
    ),
    RouteRow(
        # Re-points every diagram showing the icon and renders each, so it is budgeted as rendering is.
        "POST", "/api/icons/{artifact_id}/replace", "operation", "icons_replace_icon", TYPED,
        identity_parameters=_ID, mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        # 204 when deleted; a dry run answers 200 with its plan, and an icon still in use 409 with its users.
        "DELETE", "/api/icons/{artifact_id}", "detail", "icons_delete_icon", BODYLESS,
        identity_parameters=_ID, mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/icons/{artifact_id}/image", "subresource", "icons_read_icon_image", MEDIA,
        identity_parameters=_ID, cache_directive="private",
    ),
)
