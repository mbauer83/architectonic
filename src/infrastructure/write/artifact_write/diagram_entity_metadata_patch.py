"""Targeted metadata patch for a single diagram-entity (datatype classifier or one of its
attributes).

The GUI diagram *viewer* lets an operator edit only the descriptive meta-information of a selected
classifier or field — never its structure (name, type, key membership, ordering, existence). Rather
than have the browser round-trip the whole ``diagram-entities`` map (last-write-wins over the entire
diagram, and only lossless if the GUI faithfully echoes every field it does not model), this op
reads the file, merges a small whitelisted delta into the addressed record, and delegates to
``edit_diagram`` for verification, PUML re-render, and persistence. The whitelist is NOT hand-listed
here — it derives from the diagram type's own ``editable_metadata`` config (the single source of
truth), so "meta-only" (never rename/retype/restructure) stays true by construction and can never
drift from the type's declaration.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.candidate_repository import CandidateRepository
from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path
from src.application.verification.artifact_verifier import ArtifactVerifier

from .diagram_edit import edit_diagram
from .parse_existing import parse_diagram_file
from .types import WriteResult

# This op navigates the datatype structure (a classifier and its attribute sub-collection); which
# FIELDS of each are editable descriptive metadata is not decided here — it derives from config.
_CLASSIFIER_ENTITY_TYPE = "classifier"
_ATTRIBUTES_SUBPART = "attributes"


def _editable_field_names(
    verifier: ArtifactVerifier, diagram_type: str, entity_type: str, subpart: str | None,
) -> frozenset[str]:
    """The editable descriptive-metadata field names declared by the diagram type for this entity
    type (and optional sub-part) — the single source of truth. Empty when the type is unknown or
    declares none, which then refuses every key (safe by construction)."""
    try:
        module = verifier._runtime_catalogs.diagram_types.find_diagram_type(diagram_type)
    except Exception:  # noqa: BLE001 — an unknown/malformed diagram type yields no editable fields
        module = None
    if module is None:
        return frozenset()
    for own in getattr(module.ui_config, "diagram_only_types", ()):
        if own.entity_type == entity_type:
            return own.editable_metadata.field_names(subpart)
    return frozenset()


def _is_cleared(value: object) -> bool:
    """A cleared field: absent value, an explicit false flag, or an empty string/list. Cleared
    fields are removed so the frontmatter never accretes ``role: ''`` / ``optional: false`` noise
    (both are the schema defaults)."""
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def _apply_meta_patch(record: dict[str, Any], patch: dict[str, object], allowed: frozenset[str]) -> None:
    """Merge ``patch`` into ``record`` in place, refusing any non-whitelisted key so a structural
    edit can never travel this path."""
    for key, value in patch.items():
        if key not in allowed:
            raise ValueError(f"field {key!r} is not editable via a diagram-entity metadata patch")
        if _is_cleared(value):
            record.pop(key, None)
        else:
            record[key] = value


def _find_classifier(diagram_entities: dict[str, Any], classifier_id: str) -> dict[str, Any]:
    classifiers = diagram_entities.get("classifier")
    match = next(
        (c for c in classifiers if isinstance(c, dict) and str(c.get("id")) == classifier_id),
        None,
    ) if isinstance(classifiers, list) else None
    if match is None:
        raise ValueError(f"classifier {classifier_id!r} not found in diagram")
    return match


def _find_attribute(classifier: dict[str, Any], attribute_id: str) -> dict[str, Any]:
    attributes = classifier.get("attributes")
    match = next(
        (a for a in attributes if isinstance(a, dict) and str(a.get("id")) == attribute_id),
        None,
    ) if isinstance(attributes, list) else None
    if match is None:
        raise ValueError(f"attribute {attribute_id!r} not found on classifier {classifier.get('id')!r}")
    return match


def patch_diagram_entity_metadata(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    classifier_id: str,
    attribute_id: str | None,
    patch: dict[str, object],
    dry_run: bool,
    committed_repo: CandidateRepository | None = None,
) -> WriteResult:
    """Merge a whitelisted metadata delta into one classifier (``attribute_id`` omitted) or one of
    its attributes (``attribute_id`` set), then persist through ``edit_diagram``. Records are
    addressed by stable ``id`` (not position), so a reorder never mis-targets."""
    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)
    diagram_type = str(parsed.frontmatter.get("diagram-type", ""))
    raw = parsed.frontmatter.get("diagram-entities")
    if not isinstance(raw, dict):
        raise ValueError(f"Diagram '{artifact_id}' has no editable diagram-entities")
    diagram_entities = copy.deepcopy(raw)

    classifier = _find_classifier(diagram_entities, classifier_id)
    subpart = None if attribute_id is None else _ATTRIBUTES_SUBPART
    target = classifier if attribute_id is None else _find_attribute(classifier, attribute_id)
    allowed = _editable_field_names(verifier, diagram_type, _CLASSIFIER_ENTITY_TYPE, subpart)
    _apply_meta_patch(target, patch, allowed)

    return edit_diagram(
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        diagram_entities=diagram_entities,
        dry_run=dry_run,
        committed_repo=committed_repo,
    )
