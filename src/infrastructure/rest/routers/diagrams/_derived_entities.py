"""The entities a model-backed diagram derives, as the preview and the context read both serve them.

One function because the two reads answer the same question about the same diagram — what the type's
projection draws and as what — and an editor shows the context's answer until its first preview
replaces it. Two serialisations of one projection would let the panel change its headings on the
first preview for no reason the reader could see.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.application.derivation.preview import project_view_for_preview
from src.infrastructure.artifact_index import shared_artifact_index


def derived_entity_rows(
    module: object, diagram_type: str, diagram_entities: Mapping[str, object], repo_root: Path
) -> list[dict[str, Any]] | None:
    """Each derived entity with the type the projection draws it as; None where the type derives nothing."""
    items = project_view_for_preview(module, diagram_type, diagram_entities, shared_artifact_index([repo_root]))
    if items is None:
        return None
    return [
        {"id": i.entity_id, "name": i.name, "item_type": i.display_class, "role": i.role, "excluded": i.excluded}
        for i in items
    ]
