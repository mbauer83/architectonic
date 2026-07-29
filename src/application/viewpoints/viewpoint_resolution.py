"""Slug/ad-hoc resolution for viewpoint execution.

The one place that resolves a request's ``slug`` (a catalog definition) or ``query`` (an
ad-hoc, identity-less definition) to a ``ViewpointDefinition`` plus its identity — and applies
the optional ephemeral ``presentation`` override. Shared by ``evaluate_viewpoint`` and
``project_viewpoint_repository`` so slug/ad-hoc resolution has exactly one implementation.
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)


class UnknownViewpointSlugError(ValueError):
    """Raised when a requested slug is absent from the effective merged catalog."""


def _ad_hoc_definition(
    query: ExecutableViewpointQuery, presentation: PresentationSpec | None
) -> ViewpointDefinition:
    return ViewpointDefinition(slug="", version=0, name="", query=query, presentation=presentation)


def resolve_viewpoint_definition(
    slug: str | None,
    query: ExecutableViewpointQuery | None,
    *,
    catalog: ViewpointCatalog,
    presentation: PresentationSpec | None = None,
) -> tuple[ViewpointDefinition, str | None, int | None]:
    """Resolve exactly one of ``slug``/``query`` to a ``ViewpointDefinition`` plus its
    identity (``None``/``None`` for an ad-hoc query).

    ``presentation`` (optional) is an ephemeral override. For the slug branch, when supplied
    it replaces the resolved definition's presentation for this execution only
    (``dataclasses.replace`` — the stored catalog definition is never mutated); when omitted
    the resolved definition (and its saved presentation) is returned unchanged. For the query
    branch it is carried onto the ad-hoc definition. The returned identity still reflects the
    saved slug/version so provenance is unaffected by the override.
    """
    if slug is not None:
        resolved = catalog.get(slug)
        if resolved is None:
            raise UnknownViewpointSlugError(f"unknown viewpoint slug '{slug}'")
        if presentation is not None:
            resolved = replace(resolved, presentation=presentation)
        return resolved, resolved.slug, resolved.version
    if query is None:
        raise ValueError("requires exactly one of slug/query")
    return _ad_hoc_definition(query, presentation), None, None
