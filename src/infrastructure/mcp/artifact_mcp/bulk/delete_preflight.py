"""Preflight planning for bulk delete operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infrastructure.mcp.artifact_mcp.context import expand_artifact_id
from src.infrastructure.mcp.artifact_mcp.edit_tools import _require_registry, _resolve

from .common import KNOWN_DELETE_OPS
from .delete_plan import (
    ConnectionKey,
    collect_requests,
    planned_steps,
    validation_error,
)
from .diagram_refs import (
    connection_ref_ids,
    toposort_entities,
)


def preflight_bulk_delete(
    repo_root: Path,
    items: list[dict[str, Any]],
    *,
    auto_sync_diagrams: bool,
) -> tuple[
    dict[int, dict[str, object]],
    list[dict[str, Any]],
    list[ConnectionKey],
    list[str],
    list[str],
]:
    indexed = list(enumerate(items))
    results: dict[int, dict[str, object]] = {}
    planned: list[dict[str, Any]] = []

    unknown = [(index, item) for index, item in indexed if item.get("op") not in KNOWN_DELETE_OPS]
    if unknown:
        for index, item in unknown:
            results[index] = validation_error(
                str(item.get("op", "unknown")),
                f"Unknown op '{item.get('op')}'",
            )
        return results, planned, [], [], []

    root, registry, _verifier = _resolve(str(repo_root), need_registry=True)
    registry = _require_registry(registry)
    _expand_item_ids(items, registry)

    explicit_connection_deletes, entity_deletes, document_deletes, diagram_deletes, duplicate_errors = collect_requests(
        indexed
    )
    if duplicate_errors:
        for index, op, message in duplicate_errors:
            results[index] = validation_error(op, message)
        return results, planned, [], [], []

    entity_delete_set = set(entity_deletes)
    diagram_delete_set = set(diagram_deletes)
    explicit_connection_delete_set = set(explicit_connection_deletes)
    implicit_connection_deletes: set[ConnectionKey] = set()
    auto_sync_diagram_ids: set[str] = set()
    grf_refs = {
        artifact_id: [rec.artifact_id for rec in registry.grf_references_to_entity(artifact_id)]
        for artifact_id in entity_delete_set
    }

    _validate_entity_deletes(
        entity_deletes=entity_deletes,
        entity_delete_set=entity_delete_set,
        diagram_delete_set=diagram_delete_set,
        explicit_connection_delete_set=explicit_connection_delete_set,
        registry=registry,
        root=root,
        auto_sync_diagrams=auto_sync_diagrams,
        results=results,
        implicit_connection_deletes=implicit_connection_deletes,
        auto_sync_diagram_ids=auto_sync_diagram_ids,
    )
    _validate_connection_deletes(
        explicit_connection_deletes=explicit_connection_deletes,
        diagram_delete_set=diagram_delete_set,
        registry=registry,
        auto_sync_diagrams=auto_sync_diagrams,
        results=results,
        auto_sync_diagram_ids=auto_sync_diagram_ids,
    )
    for artifact_id, index in document_deletes.items():
        if not _artifact_path_in_root(registry, artifact_id, root):
            results[index] = validation_error(
                "delete_document",
                f"Document '{artifact_id}' not found under {root}",
            )
    for artifact_id, index in diagram_deletes.items():
        if not _artifact_path_in_root(registry, artifact_id, root):
            results[index] = validation_error(
                "delete_diagram",
                f"Diagram '{artifact_id}' not found in repo '{root}'",
            )
    if results:
        return results, planned, sorted(implicit_connection_deletes), [], sorted(auto_sync_diagram_ids)

    entity_order = toposort_entities(entity_delete_set, grf_refs)
    planned.extend(planned_steps(indexed=indexed, entity_order=entity_order))
    return (
        results,
        planned,
        sorted(implicit_connection_deletes),
        entity_order,
        sorted(auto_sync_diagram_ids),
    )


def _validate_entity_deletes(
    *,
    entity_deletes: dict[str, int],
    entity_delete_set: set[str],
    diagram_delete_set: set[str],
    explicit_connection_delete_set: set[ConnectionKey],
    registry: Any,
    root: Path,
    auto_sync_diagrams: bool,
    results: dict[int, dict[str, object]],
    implicit_connection_deletes: set[ConnectionKey],
    auto_sync_diagram_ids: set[str],
) -> None:
    for artifact_id, index in entity_deletes.items():
        blockers = _entity_delete_blockers(
            artifact_id=artifact_id,
            index=index,
            entity_delete_set=entity_delete_set,
            diagram_delete_set=diagram_delete_set,
            explicit_connection_delete_set=explicit_connection_delete_set,
            registry=registry,
            root=root,
            auto_sync_diagrams=auto_sync_diagrams,
            results=results,
            implicit_connection_deletes=implicit_connection_deletes,
            auto_sync_diagram_ids=auto_sync_diagram_ids,
        )
        if blockers:
            results[index] = validation_error(
                "delete_entity",
                (
                    f"Cannot delete entity '{artifact_id}' in this batch because dependent artifacts remain:\n"
                    + "\n".join(f"- {blocker}" for blocker in blockers)
                ),
            )


def _entity_delete_blockers(
    *,
    artifact_id: str,
    index: int,
    entity_delete_set: set[str],
    diagram_delete_set: set[str],
    explicit_connection_delete_set: set[ConnectionKey],
    registry: Any,
    root: Path,
    auto_sync_diagrams: bool,
    results: dict[int, dict[str, object]],
    implicit_connection_deletes: set[ConnectionKey],
    auto_sync_diagram_ids: set[str],
) -> list[str]:
    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        results[index] = validation_error("delete_entity", f"Entity '{artifact_id}' not found in model")
        return []
    try:
        entity_file.relative_to(root)
    except ValueError:
        results[index] = validation_error(
            "delete_entity",
            f"Entity '{artifact_id}' is not in writable repo '{root}'",
        )
        return []

    blockers: list[str] = []
    for rec in registry.find_connections_for(artifact_id, direction="inbound"):
        key = (rec.source, rec.conn_type, rec.target)
        if key in explicit_connection_delete_set:
            continue
        if rec.source in entity_delete_set:
            implicit_connection_deletes.add(key)
            continue
        blockers.append(f"incoming connection must also be deleted: {rec.source} {rec.conn_type} -> {artifact_id}")

    _collect_entity_diagram_effects(
        artifact_id=artifact_id,
        diagram_delete_set=diagram_delete_set,
        registry=registry,
        auto_sync_diagrams=auto_sync_diagrams,
        blockers=blockers,
        auto_sync_diagram_ids=auto_sync_diagram_ids,
    )
    for rec in registry.grf_references_to_entity(artifact_id):
        if rec.artifact_id not in entity_delete_set:
            blockers.append(f"global entity reference must also be deleted: {rec.artifact_id}")
    return blockers


def _collect_entity_diagram_effects(
    *,
    artifact_id: str,
    diagram_delete_set: set[str],
    registry: Any,
    auto_sync_diagrams: bool,
    blockers: list[str],
    auto_sync_diagram_ids: set[str],
) -> None:
    refs_to_check = {rec.artifact_id for rec in registry.diagrams_referencing_artifact(artifact_id)}
    for rec in registry.find_connections_for(artifact_id, direction="outbound"):
        for conn_id in connection_ref_ids(rec.source, rec.conn_type, rec.target):
            refs_to_check.update(d.artifact_id for d in registry.diagrams_referencing_artifact(conn_id))
    if auto_sync_diagrams:
        for rec in registry.find_connections_for(artifact_id, direction="any"):
            for conn_id in connection_ref_ids(rec.source, rec.conn_type, rec.target):
                refs_to_check.update(d.artifact_id for d in registry.diagrams_referencing_artifact(conn_id))
    for ref in sorted(refs_to_check):
        if ref in diagram_delete_set:
            continue
        if auto_sync_diagrams:
            auto_sync_diagram_ids.add(ref)
        else:
            blockers.append(f"diagram must also be deleted: {ref}")


def _validate_connection_deletes(
    *,
    explicit_connection_deletes: dict[ConnectionKey, int],
    diagram_delete_set: set[str],
    registry: Any,
    auto_sync_diagrams: bool,
    results: dict[int, dict[str, object]],
    auto_sync_diagram_ids: set[str],
) -> None:
    for key, index in explicit_connection_deletes.items():
        if _connection_for_key(registry, key) is None:
            results[index] = validation_error(
                "delete_connection",
                f"Connection '{key[1]} -> {key[2]}' not found for source '{key[0]}'",
            )
            continue
        blocking_diagrams = sorted(
            {
                diagram.artifact_id
                for connection_id in connection_ref_ids(key[0], key[1], key[2])
                for diagram in registry.diagrams_referencing_artifact(connection_id)
                if diagram.artifact_id not in diagram_delete_set
            }
        )
        if not blocking_diagrams:
            continue
        if auto_sync_diagrams:
            auto_sync_diagram_ids.update(blocking_diagrams)
            continue
        results[index] = validation_error(
            "delete_connection",
            (
                f"Cannot delete connection '{key[1]} -> {key[2]}' in this batch because "
                "dependent diagrams remain:\n"
                + "\n".join(f"- diagram must also be deleted: {diagram_id}" for diagram_id in blocking_diagrams)
            ),
        )


def _expand_item_ids(items: list[dict], registry) -> None:
    """Expand short-form IDs in delete-batch items in place (PREFIX@epoch.random → full form)."""
    for item in items:
        for field in ("artifact_id", "source_entity", "target_entity"):
            if field in item:
                item[field] = expand_artifact_id(registry, str(item[field]))


def _artifact_path_in_root(registry: Any, artifact_id: str, root: Path) -> bool:
    path = registry.find_file_by_id(artifact_id)
    if path is None:
        return False
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _connection_for_key(registry: Any, key: ConnectionKey):
    source, conn_type, target = key
    for rec in registry.find_connections_for(source, direction="outbound", conn_type=conn_type):
        if rec.target == target:
            return rec
    return None
