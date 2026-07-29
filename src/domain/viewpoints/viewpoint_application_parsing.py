"""Parse and serialize a ``ViewpointApplication`` from/to the ``viewpoint: {slug, version,
...}`` frontmatter mapping a diagram or matrix file carries.

``target_kind``/``target_id`` are not stored in the mapping itself — they are the file being
read/written, supplied by the caller from context — so this module only round-trips the
``slug``/``pinned_version``/``enforcement_override``/``derivation_params`` fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.viewpoints.viewpoints import (
    VALID_ENFORCEMENT_SETTINGS,
    EnforcementSetting,
    TargetKind,
    ViewpointApplication,
)


def parse_viewpoint_application(
    raw: object,
    *,
    target_kind: TargetKind,
    target_id: str,
) -> ViewpointApplication | None:
    """Parse the ``viewpoint:`` frontmatter value, or ``None`` if the key is absent/empty.

    Raises ``ValueError`` for a present-but-malformed value (missing ``slug``, non-integer
    ``version``, or an unknown ``enforcement_override``) — the same "rejected loudly" stance
    as the rest of the viewpoint parsing.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("viewpoint frontmatter value must be a mapping")
    if "slug" not in raw:
        raise ValueError("viewpoint frontmatter value is missing 'slug'")
    enforcement_override = _enforcement_override(raw.get("enforcement_override"))
    derivation_params = raw.get("derivation_params")
    return ViewpointApplication(
        target_kind=target_kind,
        target_id=target_id,
        viewpoint_slug=str(raw["slug"]),
        pinned_version=int(raw.get("version", 1)),
        enforcement_override=enforcement_override,
        derivation_params=dict(derivation_params) if isinstance(derivation_params, Mapping) else {},
    )


def _enforcement_override(value: object) -> EnforcementSetting | None:
    if value is None:
        return None
    text = str(value)
    if text not in ("off", "warn", "ghost"):
        raise ValueError(f"viewpoint enforcement_override {text!r} is not one of {sorted(VALID_ENFORCEMENT_SETTINGS)}")
    return text


def viewpoint_application_to_mapping(application: ViewpointApplication) -> dict[str, Any]:
    """Serialize to the ``viewpoint:`` frontmatter value (excludes target_kind/target_id)."""
    result: dict[str, Any] = {"slug": application.viewpoint_slug, "version": application.pinned_version}
    if application.enforcement_override is not None:
        result["enforcement_override"] = application.enforcement_override
    if application.derivation_params:
        result["derivation_params"] = dict(application.derivation_params)
    return result


def normalize_viewpoint_frontmatter(
    raw: object,
    *,
    target_kind: TargetKind,
    target_id: str,
) -> dict[str, Any] | None:
    """Validate and round-trip a caller-supplied ``viewpoint:`` frontmatter value.

    Used by the diagram write paths (MCP ``artifact_create_diagram``/``artifact_edit_diagram``)
    to normalize input through the same parse/serialize grammar the verifier reads back —
    defaults filled in (e.g. an omitted ``version`` becomes 1), one grammar, not a parallel
    shape. Raises ``ValueError`` for a malformed value, same as ``parse_viewpoint_application``.
    """
    if raw is None:
        return None
    application = parse_viewpoint_application(raw, target_kind=target_kind, target_id=target_id)
    if application is None:
        return None
    return viewpoint_application_to_mapping(application)
