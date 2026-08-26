"""Full-repository scanning for ArtifactIndex.refresh().

Split out of _service_incremental.py, which owns the incremental
(single-file) update path; this module owns the from-scratch rebuild path.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import TypeVar

from src.application._diagram_entity_extraction import (
    extract_diagram_connections as _extract_diagram_connections,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_entities as _extract_diagram_entities,
)
from src.application.artifacts.parsing import (
    parse_diagram,
    parse_document,
    parse_entity,
    parse_outgoing_file,
)
from src.application.ports import Candidate
from src.application.repo_path_helpers import (
    all_model_roots,
    diagram_source_root,
    docs_root,
    group_fn_diagram,
    group_fn_document,
    group_fn_entity,
    group_fn_scratchpad,
    scratchpads_root,
)
from src.application.scratchpad.indexing import parse_scratchpad
from src.config.repo_paths import RENDERED
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    DuplicateArtifactIdError,
    EntityRecord,
    RepoMount,
)
from src.domain.repository.repo_layout import SCRATCHPAD_SUFFIX
from src.infrastructure.write.artifact_write.staged_workspace import overlay_paths

from ._mem_store import _MemStore

_ArtT = TypeVar("_ArtT", EntityRecord, ConnectionRecord, DiagramRecord, DocumentRecord)


def _insert_mounted(
    rec: _ArtT,
    label: str,
    mount_root: Path,
    store: dict[str, _ArtT],
    *,
    candidates_map: dict[str, list[Candidate]] | None = None,
    scope: str | None = None,
) -> None:
    if candidates_map is not None and scope is not None:
        key = stable_id(rec.artifact_id)
        candidates_map.setdefault(key, []).append(
            Candidate(artifact_id=rec.artifact_id, path=rec.path, scope=scope)  # type: ignore[arg-type]
        )
    existing = store.get(rec.artifact_id)
    if existing is None:
        store[rec.artifact_id] = rec
        return
    try:
        existing.path.resolve().relative_to(mount_root.resolve())
    except ValueError:
        return
    raise DuplicateArtifactIdError(
        f"Duplicate {label} artifact-id '{rec.artifact_id}' in {rec.path} and {existing.path}"
    )


def _scan_model_records(mount: RepoMount, mem: _MemStore, *, domain_names: frozenset[str]) -> None:
    """Index entities and outgoing connections across every model root of a repo."""
    for model_root in all_model_roots(mount.root):
        for path in sorted(overlay_paths(model_root, ("*.md",))):
            if path.name.endswith(".outgoing.md"):
                continue
            entity = parse_entity(path, model_root, domain_names=domain_names)
            if entity is not None:
                grp = group_fn_entity(path, mount.root)
                _insert_mounted(
                    replace(entity, group=grp), "entity", mount.root, mem.entities,
                    candidates_map=mem.identity_candidates, scope=mount.scope,
                )
        for path in sorted(overlay_paths(model_root, ("*.outgoing.md",))):
            grp = group_fn_entity(path, mount.root)
            for conn in parse_outgoing_file(path):
                _insert_mounted(
                    replace(conn, group=grp), "connection", mount.root, mem.connections,
                    candidates_map=mem.identity_candidates, scope=mount.scope,
                )


def _iter_diagram_sources(diag_root: Path) -> Iterator[Path]:
    """Diagram .puml/.md sources under *diag_root*, excluding the rendered output tree."""
    # Matched on the path as listed, not on `resolve()`: inside a staged transaction `overlay_paths`
    # symlinks live files in as it lists them, so resolving would compare a live path against a
    # staged rendered root, never match, and index the rendered tree as if it were source.
    for path in sorted(overlay_paths(diag_root, ("*.puml", "*.md"))):
        if RENDERED not in path.parts:
            yield path


_AttrTypeRefFn = Callable[["DiagramRecord"], list[tuple[str, str, str]]]


def _scan_diagram_records(
    repo_root: Path,
    mem: _MemStore,
    *,
    workspace_types: dict[str, frozenset[str]] | None = None,
    attr_type_ref_fn: _AttrTypeRefFn | None = None,
) -> None:
    """Index diagrams and the entities/connections they materialise."""
    diag_root = diagram_source_root(repo_root)
    if not diag_root.exists():
        return
    for path in _iter_diagram_sources(diag_root):
        diag = parse_diagram(path)
        if diag is None:
            continue
        diag = replace(diag, group=group_fn_diagram(path, repo_root))
        _insert_mounted(diag, "diagram", repo_root, mem.diagrams)
        ws = (workspace_types or {}).get(diag.diagram_type, frozenset())
        mem.entities.update({de.artifact_id: de for de in _extract_diagram_entities(diag, ws)})
        mem.connections.update({dc.artifact_id: dc for dc in _extract_diagram_connections(diag, ws)})
        if attr_type_ref_fn is not None:
            mem.attribute_type_refs[diag.artifact_id] = attr_type_ref_fn(diag)


def _scan_document_records(repo_root: Path, mem: _MemStore) -> None:
    # No `exists()` guard: inside a staged transaction the directory is not materialized until
    # something writes to it, so the guard would return early and index no documents at all.
    # `overlay_paths` yields nothing for a root that genuinely holds none.
    doc_root = docs_root(repo_root)
    for path in sorted(overlay_paths(doc_root, ("*.md",))):
        doc = parse_document(path)
        if doc is not None:
            grp = group_fn_document(path, repo_root)
            _insert_mounted(replace(doc, group=grp), "document", repo_root, mem.documents)


def _scan_scratchpad_records(repo_root: Path, mem: _MemStore) -> None:
    """Index every note on every scratchpad under this mount.

    Not routed through `_insert_mounted`: that guards against two files claiming one artifact id,
    and a note's address is composed from its scratchpad's, so the id it would guard is already
    guarded one level up. Two scratchpads sharing an id is a duplicate *scratchpad*, which the
    scratchpad repository refuses at the point it can say so.
    """
    root = scratchpads_root(repo_root)
    for path in sorted(overlay_paths(root, (f"*{SCRATCHPAD_SUFFIX}",))):
        pad, notes = parse_scratchpad(path, group=group_fn_scratchpad(path, repo_root))
        if pad is not None:
            mem.scratchpads[pad.artifact_id] = pad
        for note in notes:
            mem.scratchpad_notes[note.artifact_id] = note


def scan_mount(
    mount: RepoMount,
    mem: _MemStore,
    *,
    domain_names: frozenset[str],
    workspace_types: dict[str, frozenset[str]] | None = None,
    attr_type_ref_fn: _AttrTypeRefFn | None = None,
) -> None:
    _scan_model_records(mount, mem, domain_names=domain_names)
    _scan_diagram_records(mount.root, mem, workspace_types=workspace_types, attr_type_ref_fn=attr_type_ref_fn)
    _scan_document_records(mount.root, mem)
    _scan_scratchpad_records(mount.root, mem)
