from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.verification._verifier_inventory import FileInventory
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import entity_id_from_path
from src.config.repo_paths import DOCS
from src.domain.repository.artifact_location import artifact_kind_at, model_file_kind


class CandidateInventoryPort:
    def __init__(self, *, registry: ArtifactRegistry, changed_paths: set[Path]) -> None:
        self._registry = registry
        self._changed_paths = changed_paths

    def build(self, repo_path: Path, *, include_diagrams: bool) -> FileInventory:
        return candidate_inventory(
            registry=self._registry,
            changed_paths=self._changed_paths,
            include_diagrams=include_diagrams,
        )

    def list_doc_files(self, repo_path: Path) -> list[Path]:
        return self.filter_doc_files(repo_path, list(self._changed_paths))

    def filter_doc_files(self, repo_path: Path, candidates: list[Path]) -> list[Path]:
        return [
            path for path in candidates
            if (rel := rel_to_root(path.resolve(), repo_path.resolve())) is not None
            and Path(rel).parts[:1] == (DOCS,)
            and path.suffix == ".md"
        ]


def candidate_inventory(
    *,
    registry: ArtifactRegistry,
    changed_paths: set[Path],
    include_diagrams: bool,
) -> FileInventory:
    rels = {rel_to_root(path, registry.repo_roots[0]) for path in changed_paths}
    selected = {r for r in rels if r is not None}
    for path in list(changed_paths):
        aid = entity_id_from_path(path) if model_file_kind(path) == "entity" else None
        if aid:
            selected.update(
                rel for rec in registry.find_connections_for(aid)
                if (rel := rel_to_root(rec.path, registry.repo_roots[0])) is not None
            )
            selected.update(
                rel for rec in registry.diagrams_referencing_artifact(aid)
                if (rel := rel_to_root(rec.path, registry.repo_roots[0])) is not None
            )
    return _inventory_from_relpaths(registry.repo_roots[0], selected, include_diagrams=include_diagrams)


def _inventory_from_relpaths(repo_root: Path, relpaths: set[str], *, include_diagrams: bool) -> FileInventory:
    inv = FileInventory(repo_path=repo_root, include_diagrams=include_diagrams)
    for rel in sorted(relpaths):
        path = repo_root / rel
        if not path.exists():
            continue
        file_type: Literal["entity", "connection", "diagram"]
        match artifact_kind_at(rel):
            case "entity" | "connection" as model_kind:
                file_type = model_kind
            case "diagram" if include_diagrams:
                file_type = "diagram"
            case _:
                continue  # a diagram the caller left out, or no kind the bulk inventory verifies
        inv.add_file(path, file_type)
        if file_type == "entity":
            inv.entity_relpaths.append(rel)
            inv.entity_path_by_id[entity_id_from_path(path)] = rel
        elif file_type == "connection":
            inv.connection_relpaths.append(rel)
        elif path.suffix == ".puml":
            inv.diagram_puml_relpaths.append(rel)
        else:
            inv.diagram_matrix_relpaths.append(rel)
    inv.ordered_paths = (
        inv.entity_relpaths
        + inv.connection_relpaths
        + inv.diagram_puml_relpaths
        + inv.diagram_matrix_relpaths
    )
    return inv


def rel_to_root(path: Path, root: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return None
