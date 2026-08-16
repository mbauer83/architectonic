"""Diagram reference-ID inference helpers."""

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.artifacts.parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.domain.artifact_id import stable_conn_id, stable_id
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.diagram_type_registry import find_renderer
from src.infrastructure.rendering.archimate_relation_rendering import strip_suppressed_relation_labels

from ._artifact_deduplication import get_repository

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

    return get_module_registry()


@lru_cache(maxsize=1)
def _symmetric_conn_types() -> frozenset[str]:
    return frozenset(
        str(name)
        for name, info in _registry().all_connection_types().items()
        if getattr(info, "symmetric", False)
    )


@lru_cache(maxsize=1)
def _suppressed_stereotype_tokens() -> frozenset[str]:
    from src.infrastructure.app_bootstrap import build_runtime_catalogs  # noqa: PLC0415, process_runtime_catalogs

    return build_runtime_catalogs(_registry()).diagram_types.suppressed_stereotype_tokens()


def _collect_diagram_renderer_references(
    diagram_type: str,
    repo_root: Path,
    diagram_entities: dict[str, object],
    diagram_connections: list[dict[str, object]] | None,
    bindings: list[dict[str, object]] | None = None,
) -> tuple[list[str] | None, list[str] | None]:
    from src.domain.ontology_representation.ontology_protocol import (  # noqa: PLC0415
        ModelReferencingDiagramRenderer,
    )

    renderer = find_renderer(diagram_type)
    # One `isinstance`, in the one place that asks. `collect_references` used to be required of every
    # renderer, so twelve of the thirteen implementations existed only to answer "nothing" — seven of
    # them with the same four lines. A renderer whose diagram-owned data names no model artifact says
    # so by not implementing the capability.
    if renderer is None or not isinstance(renderer, ModelReferencingDiagramRenderer):
        return None, None
    refs = renderer.collect_references(
        diagram_type,
        repo_root,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
        bindings=bindings,
    )
    entity_ids = list(refs.entity_ids) or None
    connection_ids = list(refs.connection_ids) or None
    return entity_ids, connection_ids


def _merge_reference_ids(
    explicit: list[str] | None,
    collected: list[str] | None,
) -> list[str] | None:
    if explicit is None and collected is None:
        return None
    merged: list[str] = []
    for group in (explicit or [], collected or []):
        for value in group:
            if value not in merged:
                merged.append(value)
    return merged


def _prune_unknown_references(
    registry: "ArtifactRegistry | None",
    entity_ids: list[str] | None,
    connection_ids: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Drop references to entities/connections that no longer resolve.

    After an entity is renamed (slug change) or deleted, a diagram's cached entity-ids-used /
    connection-ids-used can point at ids that no longer exist, which makes the diagram fail
    verification (E301/E302) and become unwritable. Pruning lets a re-projection self-heal.
    The registry spans both repo roots, so valid enterprise/global references are preserved;
    pruning is skipped when the registry is unavailable or its id set is empty so a cold or
    partial index can never strip valid references.
    """
    if registry is None:
        return entity_ids, connection_ids
    valid_short_entities = {stable_id(e) for e in registry.entity_ids()}
    valid_short_connections = {stable_conn_id(c) for c in registry.connection_ids()}
    pruned_entities = (
        [e for e in entity_ids if stable_id(e) in valid_short_entities]
        if entity_ids and valid_short_entities
        else entity_ids
    )
    pruned_connections = (
        [c for c in connection_ids if stable_conn_id(c) in valid_short_connections]
        if connection_ids and valid_short_connections
        else connection_ids
    )
    return pruned_entities, pruned_connections


def _normalize_standard_alias(artifact_id: str) -> str:
    parts = artifact_id.split(".")
    if len(parts) < 2 or "@" not in parts[0]:
        return ""
    prefix = parts[0].split("@", 1)[0]
    return normalize_puml_alias(f"{prefix}_{parts[1]}")


def _alias_entity_lookup(repo_root: Path) -> dict[str, str]:
    repo = get_repository(repo_root)
    alias_map: dict[str, str] = {}
    for entity in repo.list_entities():
        if entity.display_alias:
            alias_map.setdefault(normalize_puml_alias(entity.display_alias), entity.artifact_id)
        std_alias = _normalize_standard_alias(entity.artifact_id)
        if std_alias:
            alias_map.setdefault(std_alias, entity.artifact_id)
    return alias_map


def _infer_reference_ids_from_puml(
    repo_root: Path,
    puml_body: str,
) -> tuple[list[str] | None, list[str] | None]:
    """Entity and connection ids a hand-supplied body references, via the ONE shared parser.

    This used to carry its own blind regex copy that read only macro calls and
    stereotype-labelled arrows, so a body drawn with bare arrows (the renderer's own output
    form) contributed no connection references at all. Untyped relations are resolved against
    the model exactly the way the reconcile resolves them (``resolve_untyped_relation``): one
    candidate wins, several are disambiguated by the drawn glyph, still-ambiguous stays
    uninferred rather than guessed.
    """
    from src.application.puml_relation_parsing import declared_relations  # noqa: PLC0415

    from ._sync_helpers import resolve_untyped_relation  # noqa: PLC0415

    repo = get_repository(repo_root)
    alias_map = _alias_entity_lookup(repo_root)
    stereo_map = process_runtime_catalogs().ontology.archimate_stereotype_to_connection_type()

    entity_ids: list[str] = []
    for alias in sorted(extract_declared_puml_aliases(puml_body)):
        artifact_id = alias_map.get(normalize_puml_alias(alias))
        if artifact_id is not None and artifact_id not in entity_ids:
            entity_ids.append(artifact_id)

    all_connections = repo.list_connections()
    conn_index: dict[tuple[str, str, str], str] = {}
    reverse_conn_index: dict[tuple[str, str, str], str] = {}
    symmetric_types = _symmetric_conn_types()
    for conn in all_connections:
        conn_index[(conn.source, conn.target, conn.conn_type)] = conn.artifact_id
        if conn.conn_type in symmetric_types:
            reverse_conn_index[(conn.target, conn.source, conn.conn_type)] = conn.artifact_id

    connection_ids: list[str] = []
    for relation in declared_relations(puml_body, stereo_map):
        src_id = alias_map.get(normalize_puml_alias(relation.source_alias))
        tgt_id = alias_map.get(normalize_puml_alias(relation.target_alias))
        if src_id is None or tgt_id is None:
            continue
        if relation.connection_type is not None:
            artifact_id = conn_index.get((src_id, tgt_id, relation.connection_type))
            if artifact_id is None and relation.connection_type in symmetric_types:
                artifact_id = reverse_conn_index.get((src_id, tgt_id, relation.connection_type))
        else:
            record = resolve_untyped_relation(src_id, tgt_id, relation.arrow, all_connections)
            artifact_id = record.artifact_id if record is not None else None
        if artifact_id is not None and artifact_id not in connection_ids:
            connection_ids.append(artifact_id)

    return entity_ids or None, connection_ids or None


def diagram_entities_are_authoritative(verifier, diagram_type: str) -> bool:
    """True when *diagram_type*'s own entity types make ``diagram_entities`` its body source.

    Diagram-owned types (activity, sequence, C4, datatype, GSN — declared via
    ``ui_config.diagram_only_types``) are always rendered from ``diagram_entities``.
    ArchiMate-family types may carry ``diagram_entities`` purely as occurrence-binding
    metadata (WU-B3) on top of a hand-authored ``puml=`` body, so it must not be
    treated as a render trigger for them.
    """
    try:
        module = verifier._runtime_catalogs.diagram_types.find_diagram_type(diagram_type)
    except Exception:  # noqa: BLE001
        return False
    return bool(module is not None and module.ui_config.diagram_only_types)


def _restate_generated_declarations(puml_body: str, repo_root: Path, diagram_type: str) -> str:
    """Bring what the *renderer* states in a stored body up to date, and nothing else.

    A palette, a glyph, a relationship's line style and the label width bound are the product's
    statements rather than the author's, so a body that keeps a copy of them has to be refreshed
    whenever it is written — including on the edits that leave the picture alone, which is the only
    way a hand-laid-out diagram ever hears about a change.

    Deliberately not ``inject_includes``: that one *gives* a body a header when it has none, and
    expands an ``!include`` marker in place. An edit that carries no body must not convert a
    diagram's storage form, and `auto_include_stereotypes=False` is an author asking to keep the
    marker. A notation whose header states nothing generated does not implement the capability, and
    its bodies come through untouched.
    """
    from src.domain.ontology_representation.ontology_protocol import (  # noqa: PLC0415
        GeneratedHeaderRefreshingRenderer,
    )

    renderer = find_renderer(diagram_type)
    if renderer is None or not isinstance(renderer, GeneratedHeaderRefreshingRenderer):
        return puml_body
    return renderer.refresh_generated_header(puml_body, repo_root)


def _prepare_diagram_puml_body(puml_body: str, repo_root: Path, diagram_type: str) -> str:
    # Drop relation-stereotype edge labels the arrow style already conveys. This
    # is an ontology-global normalisation (keyed on ``show_stereotype`` across all
    # connection types), not a per-diagram-type concern, so it applies uniformly.
    puml_body = strip_suppressed_relation_labels(puml_body, _suppressed_stereotype_tokens())
    renderer = find_renderer(diagram_type)
    return puml_body if renderer is None else renderer.inject_includes(puml_body, repo_root)
