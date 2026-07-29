"""Diagram reference scanning and bulk auto-sync helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.artifact_repository import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.application.verification.artifact_verifier_parsing import (
    parse_diagram_refs,
    parse_frontmatter_from_path,
)
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, RENDERED
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write import artifact_write_ops
from src.infrastructure.write.artifact_write._sync_helpers import LookupStore


def connection_artifact_id(source_entity: str, connection_type: str, target_entity: str) -> str:
    return f"{source_entity}---{target_entity}@@{connection_type}"


def legacy_connection_ref_id(source_entity: str, connection_type: str, target_entity: str) -> str:
    return f"{source_entity} {connection_type} → {target_entity}"


def connection_ref_ids(source_entity: str, connection_type: str, target_entity: str) -> set[str]:
    return {
        connection_artifact_id(source_entity, connection_type, target_entity),
        legacy_connection_ref_id(source_entity, connection_type, target_entity),
    }


def parse_connection_ref_id(connection_id: str) -> tuple[str, str, str] | None:
    if "---" in connection_id and "@@" in connection_id:
        try:
            source, remainder = connection_id.split("---", 1)
            target, connection_type = remainder.rsplit("@@", 1)
        except ValueError:
            return None
        return source, target, connection_type
    if " → " in connection_id:
        try:
            left, target = connection_id.split(" → ", 1)
            source, connection_type = left.split(" ", 1)
        except ValueError:
            return None
        return source, target, connection_type
    return None


def connection_id_involves_entity(connection_id: str, entity_id: str) -> bool:
    parsed = parse_connection_ref_id(connection_id)
    if parsed is None:
        return False
    source, target, _connection_type = parsed
    return source == entity_id or target == entity_id


def diagram_paths(repo_root: Path) -> list[Path]:
    diagrams_root = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    if not diagrams_root.exists():
        return []
    paths: list[Path] = []
    for suffix in ("*.puml", "*.md"):
        for path in sorted(diagrams_root.rglob(suffix)):
            if path.parent.name != RENDERED:
                paths.append(path)
    return paths


def find_diagram_artifact_id(path: Path) -> str | None:
    fm = parse_frontmatter_from_path(path) or {}
    artifact_id = str(fm.get("artifact-id", "")).strip()
    return artifact_id or None


def scan_diagram_refs(repo_root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for path in diagram_paths(repo_root):
        diagram_id = find_diagram_artifact_id(path)
        if not diagram_id:
            continue
        parsed = parse_diagram_refs(path) or {}
        for entity_id in parsed.get("entity_ids", []):
            refs.setdefault(entity_id, []).append(diagram_id)
        for connection_id in parsed.get("connection_ids", []):
            refs.setdefault(connection_id, []).append(diagram_id)
    return refs


def auto_sync_diagrams(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_ids: list[str],
    dry_run: bool,
    store_factory: Callable[[], LookupStore] | None = None,
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for diagram_id in sorted(set(diagram_ids)):
        store = store_factory() if store_factory is not None else ArtifactRepository(shared_artifact_index([repo_root]))
        result = artifact_write_ops.refresh_diagram(
            repo_root=repo_root,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            artifact_id=diagram_id,
            dry_run=dry_run,
        )
        actions.append(
            {
                "artifact_id": diagram_id,
                "wrote": result.wrote,
                "deleted_diagram": result.deleted_diagram,
                "removed_entity_ids": result.removed_entity_ids,
                "removed_connection_ids": result.removed_connection_ids,
            }
        )
    return actions


def _auto_sync_ids_for_item(
    item: dict[str, Any],
    result: dict[str, object],
    refs: dict[str, list[str]],
    connection_ref_keys: list[str],
) -> set[str]:
    """Diagram ids whose renders are invalidated by a single successful edit item."""
    op = str(item.get("op", ""))
    if op == "edit_entity":
        old_id = str(item["artifact_id"])
        new_id = str(result.get("artifact_id", old_id))
        if new_id == old_id:
            return set()
        return set(refs.get(old_id, [])).union(
            ref
            for cid in connection_ref_keys
            if connection_id_involves_entity(cid, old_id)
            for ref in refs.get(cid, [])
        )
    if op == "edit_connection" and item.get("operation", "update") == "remove":
        cids = connection_ref_ids(str(item["source_entity"]), str(item["connection_type"]), str(item["target_entity"]))
        return {ref for cid in cids for ref in refs.get(cid, [])}
    return set()


def collect_bulk_write_auto_sync_diagram_ids(
    repo_root: Path,
    *,
    items: list[dict[str, Any]],
    results: dict[int, dict[str, object]],
    registry: ArtifactRegistry | None = None,
) -> list[str]:
    refs = _indexed_auto_sync_refs(registry, items, results) if registry is not None else scan_diagram_refs(repo_root)
    connection_ref_keys = [key for key in refs if parse_connection_ref_id(key) is not None]
    diagram_ids: set[str] = set()
    for index, item in enumerate(items):
        result = results.get(index)
        if result is not None and bool(result.get("wrote")):
            diagram_ids.update(_auto_sync_ids_for_item(item, result, refs, connection_ref_keys))
    return sorted(diagram_ids)


def _indexed_auto_sync_refs(
    registry: ArtifactRegistry,
    items: list[dict[str, Any]],
    results: dict[int, dict[str, object]],
) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for index, item in enumerate(items):
        result = results.get(index)
        if result is None or not bool(result.get("wrote")):
            continue
        op = str(item.get("op", ""))
        if op == "edit_entity":
            old_id = str(item["artifact_id"])
            _add_diagram_refs(refs, old_id, registry.diagrams_referencing_artifact(old_id))
            for connection in registry.find_connections_for(old_id):
                _add_diagram_refs(
                    refs,
                    connection.artifact_id,
                    registry.diagrams_referencing_artifact(connection.artifact_id),
                )
        elif op == "edit_connection" and item.get("operation", "update") == "remove":
            for connection_id in connection_ref_ids(
                str(item["source_entity"]),
                str(item["connection_type"]),
                str(item["target_entity"]),
            ):
                _add_diagram_refs(refs, connection_id, registry.diagrams_referencing_artifact(connection_id))
    return refs


def _add_diagram_refs(refs: dict[str, list[str]], artifact_id: str, diagrams) -> None:
    ids = [diagram.artifact_id for diagram in diagrams]
    if ids:
        refs.setdefault(artifact_id, []).extend(ids)


def entity_owned_connection_ids(entity_id: str, connection_paths: dict[tuple[str, str, str], Path]) -> set[str]:
    return {
        connection_id
        for (src, conn_type, target) in connection_paths
        if src == entity_id
        for connection_id in connection_ref_ids(src, conn_type, target)
    }


def toposort_entities(entity_ids: set[str], grf_refs: dict[str, list[str]]) -> list[str]:
    remaining: dict[str, set[str]] = {
        entity_id: {gar_id for gar_id in grf_refs.get(entity_id, []) if gar_id in entity_ids}
        for entity_id in entity_ids
    }
    ordered: list[str] = []
    while remaining:
        ready = sorted(entity_id for entity_id, blockers in remaining.items() if not blockers)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise ValueError(f"Cannot resolve entity delete order because of cyclic inter-entity dependencies: {cycle}")
        for entity_id in ready:
            ordered.append(entity_id)
            remaining.pop(entity_id)
        for blockers in remaining.values():
            blockers.difference_update(ready)
    return ordered
