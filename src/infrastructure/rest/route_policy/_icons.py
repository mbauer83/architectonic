"""Canonical route policy for the icon library.

An icon is addressed by its artifact id; what it applies to, its tag and its name narrow the
collection rather than naming a resource (ADR@1785451831). The picture is a subresource served as
bytes: an icon's picture never changes under its id — replacing a logo is a new icon — so a browser
may keep it, privately, for as long as it likes.
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import MEDIA, TYPED, RouteRow

_ID = ("artifact_id",)

ICON_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/icons", "collection", "icons_list_icons", TYPED, cache_directive="no-cache"),
    RouteRow("POST", "/api/icons", "collection", "icons_create_icon", TYPED, mutation_domain="repository"),
    RouteRow(
        "GET", "/api/icons/{artifact_id}", "detail", "icons_read_icon", TYPED,
        identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/icons/{artifact_id}/image", "subresource", "icons_read_icon_image", MEDIA,
        identity_parameters=_ID, cache_directive="private",
    ),
)
