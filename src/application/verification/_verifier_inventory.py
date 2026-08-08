"""The file inventory: which artifact files exist, and which reach which.

Separate from incremental state because the two answer different questions. An inventory is a graph
over the repository as it is *now* — what is there, and what a change to one file reaches. Incremental
state is a *memory* of a previous answer, loaded from a cache and discardable as stale. One is rebuilt
every pass; the other survives passes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.application.repo_path_helpers import all_model_roots
from src.application.verification.artifact_verifier_parsing import parse_connection_refs, parse_diagram_refs
from src.application.verification.artifact_verifier_types import entity_id_from_path
from src.domain.repository.repo_layout import DIAGRAM_CATALOG, DIAGRAMS


@dataclass
class FileInventory:
    repo_path: Path
    include_diagrams: bool = True
    rel_to_path: dict[str, Path] = field(default_factory=dict)
    path_to_rel: dict[Path, str] = field(default_factory=dict)
    snapshots: dict[str, dict[str, int | str]] = field(default_factory=dict)
    ordered_paths: list[str] = field(default_factory=list)
    entity_relpaths: list[str] = field(default_factory=list)
    connection_relpaths: list[str] = field(default_factory=list)
    diagram_puml_relpaths: list[str] = field(default_factory=list)
    diagram_matrix_relpaths: list[str] = field(default_factory=list)
    file_type_by_relpath: dict[str, Literal["entity", "connection", "diagram"]] = field(default_factory=dict)
    entity_path_by_id: dict[str, str] = field(default_factory=dict)
    connection_refs_by_path: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = field(default_factory=dict)
    connection_paths_by_entity: dict[str, set[str]] = field(default_factory=dict)
    neighbor_entities: dict[str, set[str]] = field(default_factory=dict)
    diagram_paths_by_entity: dict[str, set[str]] = field(default_factory=dict)
    diagram_paths_by_connection_id: dict[str, set[str]] = field(default_factory=dict)

    def add_file(self, path: Path, file_type: Literal["entity", "connection", "diagram"]) -> str:
        rel = str(path.relative_to(self.repo_path))
        self.rel_to_path[rel] = path
        self.path_to_rel[path] = rel
        self.path_to_rel[path.resolve()] = rel
        self.snapshots[rel] = {
            "content_hash": content_hash(path),
            "file_type": file_type,
        }
        self.file_type_by_relpath[rel] = file_type
        return rel


# Bumped when the shape or meaning of the persisted state changes. The loader rejects any
# other value, so a state written by an older verifier is discarded rather than
# misinterpreted — version 1 keyed file identity on mtime+size, version 2 on content hash.


def inventory_files(repo_path: Path, *, include_diagrams: bool) -> FileInventory:
    inventory = _new_inventory(repo_path=repo_path, include_diagrams=include_diagrams)
    _index_entity_files(inventory)
    _index_connection_files(inventory)
    if include_diagrams:
        _index_diagram_files(inventory)
    inventory.ordered_paths = (
        inventory.entity_relpaths
        + inventory.connection_relpaths
        + inventory.diagram_puml_relpaths
        + inventory.diagram_matrix_relpaths
    )
    return inventory


def _new_inventory(repo_path: Path, *, include_diagrams: bool) -> FileInventory:
    return FileInventory(repo_path=repo_path, include_diagrams=include_diagrams)


def _index_entity_files(inventory: FileInventory) -> None:
    # Walk every model root — the legacy top-level model/ plus each projects/<slug>/model/
    # (target group-aware layout). Rooting only at model/ silently excludes all
    # project-scoped entities from verification; the index scan uses all_model_roots too.
    for entity_root in all_model_roots(inventory.repo_path):
        for path in sorted(entity_root.rglob("*.md")):
            if path.name.endswith(".outgoing.md"):
                continue
            rel = _add_indexed_file(inventory, path, "entity")
            inventory.entity_relpaths.append(rel)
            inventory.entity_path_by_id[entity_id_from_path(path)] = rel


def _index_connection_files(inventory: FileInventory) -> None:
    for model_root in all_model_roots(inventory.repo_path):
        for path in sorted(model_root.rglob("*.outgoing.md")):
            rel = _add_indexed_file(inventory, path, "connection")
            inventory.connection_relpaths.append(rel)
            refs = parse_connection_refs(path)
            if refs is None:
                continue
            source_ids = refs.source_ids
            target_ids = refs.target_ids
            inventory.connection_refs_by_path[rel] = (source_ids, target_ids)
            _index_connection_neighbors(inventory, rel, source_ids, target_ids)


def _index_connection_neighbors(
    inventory: FileInventory,
    rel: str,
    source_ids: tuple[str, ...],
    target_ids: tuple[str, ...],
) -> None:
    for source_id in source_ids:
        inventory.connection_paths_by_entity.setdefault(source_id, set()).add(rel)
        inventory.neighbor_entities.setdefault(source_id, set())
    for target_id in target_ids:
        inventory.connection_paths_by_entity.setdefault(target_id, set()).add(rel)
        inventory.neighbor_entities.setdefault(target_id, set())
    for source_id in source_ids:
        for target_id in target_ids:
            inventory.neighbor_entities.setdefault(source_id, set()).add(target_id)
            inventory.neighbor_entities.setdefault(target_id, set()).add(source_id)


def _index_diagram_files(inventory: FileInventory) -> None:
    diagrams_dir = inventory.repo_path / DIAGRAM_CATALOG / DIAGRAMS
    if not diagrams_dir.exists():
        return
    for path in sorted(diagrams_dir.rglob("*.puml")):
        rel = _add_indexed_file(inventory, path, "diagram")
        inventory.diagram_puml_relpaths.append(rel)
        _add_diagram_refs(path, rel, inventory.diagram_paths_by_entity, inventory.diagram_paths_by_connection_id)
    for path in sorted(diagrams_dir.rglob("*.md")):
        rel = _add_indexed_file(inventory, path, "diagram")
        inventory.diagram_matrix_relpaths.append(rel)
        _add_diagram_refs(path, rel, inventory.diagram_paths_by_entity, inventory.diagram_paths_by_connection_id)


def _add_indexed_file(
    inventory: FileInventory,
    path: Path,
    file_type: Literal["entity", "connection", "diagram"],
) -> str:
    return inventory.add_file(path, file_type)


def _add_diagram_refs(
    path: Path,
    rel: str,
    diagram_paths_by_entity: dict[str, set[str]],
    diagram_paths_by_connection_id: dict[str, set[str]],
) -> None:
    refs = parse_diagram_refs(path)
    if refs is None:
        return
    for eid in refs["entity_ids"]:
        diagram_paths_by_entity.setdefault(eid, set()).add(rel)
    for cid in refs["connection_ids"]:
        diagram_paths_by_connection_id.setdefault(cid, set()).add(rel)


def expand_impacted_paths(inv: FileInventory, changed: set[str]) -> set[str]:
    impacted: set[str] = set(changed)
    for rel in changed:
        path = inv.rel_to_path.get(rel)
        if path is None:
            continue
        file_type = inv.file_type_by_relpath.get(rel)
        if file_type == "entity":
            _expand_for_entity(inv, impacted, entity_id_from_path(path))
        elif file_type == "connection":
            _expand_for_connection(inv, impacted, rel, path.stem)
    return impacted


def _expand_for_entity(inv: FileInventory, impacted: set[str], entity_id: str) -> None:
    impacted |= inv.connection_paths_by_entity.get(entity_id, set())
    impacted |= inv.diagram_paths_by_entity.get(entity_id, set())
    for connection_rel in inv.connection_paths_by_entity.get(entity_id, set()):
        impacted |= inv.diagram_paths_by_connection_id.get(Path(connection_rel).stem, set())
    for neighbor_entity in inv.neighbor_entities.get(entity_id, set()):
        neighbor_path = inv.entity_path_by_id.get(neighbor_entity)
        if neighbor_path:
            impacted.add(neighbor_path)


def _expand_for_connection(inv: FileInventory, impacted: set[str], rel: str, connection_id: str) -> None:
    impacted |= inv.diagram_paths_by_connection_id.get(connection_id, set())
    refs = inv.connection_refs_by_path.get(rel)
    if refs is None:
        return
    srcs, tgts = refs
    for entity_id in (*srcs, *tgts):
        entity_rel = inv.entity_path_by_id.get(entity_id)
        if entity_rel:
            impacted.add(entity_rel)
        impacted |= inv.connection_paths_by_entity.get(entity_id, set())
        impacted |= inv.diagram_paths_by_entity.get(entity_id, set())


def content_hash(path: Path) -> str:
    """Content fingerprint of one artifact file — the identity cache validity turns on.

    Content, not mtime+size: that keying both missed same-length edits and discarded
    still-valid caches on any metadata-only rewrite (clone, copy, checkout). Hazard
    analysis in tests/application/verification/test_incremental_cache_validity.py.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()
