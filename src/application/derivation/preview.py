"""Generic preview service: project a model-backed view for the preview checklist.

This module is diagram-type-agnostic. It never names or branches on C4 concepts
or any other diagram-type vocabulary. display_class and role are forwarded
verbatim from the module's ViewProjectionResult.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from src.domain.viewpoints.view_projection import ProjectedViewItem, ViewProjector

if TYPE_CHECKING:
    from src.application.derivation.types import ModelQuery


def project_view_for_preview(
    module: object,
    diagram_type: str,
    diagram_entities: Mapping[str, object],
    query: ModelQuery,
) -> list[ProjectedViewItem] | None:
    """Return classified, selection-flagged items, or None if unsupported/standalone.

    Selection from the normalized DerivationSelection is applied here at the
    generic layer: matched entities are marked excluded=True (not removed),
    so the checklist remains editable. The scope root always arrives with
    role="scope" and cannot be excluded.

    A large candidate set triggers a warning in the engine; no truncation happens here.
    """
    if not isinstance(module, ViewProjector):
        return None
    result = module.project_view(diagram_type, diagram_entities, query)
    if result is None:
        return None
    excluded: set[str] = (
        set(result.derivation.selection.excluded_entity_ids)
        if result.derivation.selection is not None
        else set()
    )
    return [replace(i, excluded=i.entity_id in excluded) for i in result.items]
