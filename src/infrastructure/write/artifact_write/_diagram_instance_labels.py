"""Per-instance labels on a body the edit does not regenerate.

Split out of ``diagram_edit.py`` for the reason ``_diagram_edge_labels`` was: that module's merging
function is at the length policy's limit, and this is one self-contained step of it.
"""

from __future__ import annotations

from src.application.verification.artifact_verifier import ArtifactVerifier


def relabelled_instances(puml_body: str, diagram_entities: object, verifier: ArtifactVerifier) -> str:
    """Apply ``diagram-entities.display_labels`` to a body this write did not render.

    A rendered body honours the same statement inside the renderer; this is its twin for the two
    ways a body arrives already written — supplied by the caller, or kept verbatim. Without a
    registry to resolve the instances' aliases there is nothing safe to do, and the body passes
    through untouched; so does a body whose diagram states no labels.
    """
    from src.infrastructure.rendering.archimate_occurrences import (  # noqa: PLC0415
        display_label_overrides,
        relabel_instances_in_body,
    )

    if not isinstance(diagram_entities, dict) or not display_label_overrides(diagram_entities):
        return puml_body
    registry = verifier.registry
    if registry is None:
        return puml_body
    occurrences = diagram_entities.get("occurrence")
    backing_ids = [
        str(item.get("backing_entity_id") or "")
        for item in (occurrences if isinstance(occurrences, list) else [])
        if isinstance(item, dict)
    ]
    wanted = [*display_label_overrides(diagram_entities), *backing_ids]
    entity_by_id = {
        record.artifact_id: record
        for record in (registry.get_entity(artifact_id) for artifact_id in wanted if artifact_id)
        if record is not None
    }
    return relabel_instances_in_body(puml_body, diagram_entities, entity_by_id)
