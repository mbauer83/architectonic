"""Candidate repository — committed filesystem view + in-flight overlay.

Implements PLAN §2.4.  The CandidateRepository Protocol is the central seam
for acceptance-oriented verification: verifiers read from a candidate instead
of the live SQLite index so in-flight additions/deletions are visible.

Usage::

    base = committed_repository(repo_roots)
    candidate = candidate_with(base, changed_diagrams=[new_diag], deleted_ids=frozenset())
    entity = candidate.get_entity("CLF@1.ab.x")  # visible before any index refresh
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Protocol, runtime_checkable

from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord


@runtime_checkable
class CandidateRepository(Protocol):
    """Read-only view over committed + in-flight state.  Never mutates the live index."""

    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None: ...

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]: ...

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
    ) -> list[DiagramRecord]: ...

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]: ...


@dataclass(frozen=True)
class _Overlay:
    additions: Mapping[str, EntityRecord | ConnectionRecord | DiagramRecord]
    deletions: frozenset[str]


_EMPTY_OVERLAY: _Overlay = _Overlay(additions={}, deletions=frozenset())


def _entity_matches(
    rec: EntityRecord,
    *,
    artifact_type: str | None,
    domain: str | None,
    status: str | None,
) -> bool:
    return (
        (artifact_type is None or rec.artifact_type == artifact_type)
        and (domain is None or rec.domain == domain)
        and (status is None or rec.status == status)
    )


def _diagram_matches(
    rec: DiagramRecord,
    *,
    diagram_type: str | None,
    status: str | None,
) -> bool:
    return (diagram_type is None or rec.diagram_type == diagram_type) and (
        status is None or rec.status == status
    )


class _CommittedCandidateRepository:
    """Filesystem-derived view with an empty overlay.  Delegates to ArtifactStorePort."""

    def __init__(self, store: object) -> None:
        self._store = store

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._store.get_entity(artifact_id)  # type: ignore[attr-defined]

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self._store.get_diagram(artifact_id)  # type: ignore[attr-defined]

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]:
        return self._store.list_entities(  # type: ignore[attr-defined]
            artifact_type=artifact_type, domain=domain, status=status
        )

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
    ) -> list[DiagramRecord]:
        return self._store.list_diagrams(  # type: ignore[attr-defined]
            diagram_type=diagram_type, status=status
        )

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return self._store.scope_for_path(path)  # type: ignore[attr-defined]


class _OverlayCandidateRepository:
    """Applies an overlay (additions − deletions) over a base CandidateRepository."""

    def __init__(self, base: CandidateRepository, overlay: _Overlay) -> None:
        self._base = base
        self._overlay = overlay

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        # Additions win over deletions: a workspace-scoped entity may retain its id across replacement.
        added = self._overlay.additions.get(artifact_id)
        if isinstance(added, EntityRecord):
            return added
        if artifact_id in self._overlay.deletions:
            return None
        return self._base.get_entity(artifact_id)

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        added = self._overlay.additions.get(artifact_id)
        if isinstance(added, DiagramRecord):
            return added
        if artifact_id in self._overlay.deletions:
            return None
        return self._base.get_diagram(artifact_id)

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]:
        # Additions are built first; they win over the base for ids that also appear in deletions
        # (workspace-scoped entities that retain the same id across a diagram replacement).
        out: dict[str, EntityRecord] = {}
        for rec in self._overlay.additions.values():
            if isinstance(rec, EntityRecord) and _entity_matches(
                rec, artifact_type=artifact_type, domain=domain, status=status
            ):
                out[rec.artifact_id] = rec
        for e in self._base.list_entities(artifact_type=artifact_type, domain=domain, status=status):
            if e.artifact_id not in self._overlay.deletions and e.artifact_id not in out:
                out[e.artifact_id] = e
        return sorted(out.values(), key=lambda r: r.artifact_id)

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
    ) -> list[DiagramRecord]:
        out: dict[str, DiagramRecord] = {}
        for rec in self._overlay.additions.values():
            if isinstance(rec, DiagramRecord) and _diagram_matches(rec, diagram_type=diagram_type, status=status):
                out[rec.artifact_id] = rec
        for d in self._base.list_diagrams(diagram_type=diagram_type, status=status):
            if d.artifact_id not in self._overlay.deletions and d.artifact_id not in out:
                out[d.artifact_id] = d
        return sorted(out.values(), key=lambda r: r.artifact_id)

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return self._base.scope_for_path(path)


def _child_entity_ids(base: CandidateRepository, diagram: DiagramRecord) -> frozenset[str]:
    """Return the artifact_ids of all entities owned by *diagram* in the base view."""
    return frozenset(
        e.artifact_id
        for e in base.list_entities(domain=diagram.diagram_type)
        if e.host_diagram_id == diagram.artifact_id
    )


def committed_repository(store: object) -> CandidateRepository:
    """Return a CandidateRepository backed by the given committed store with an empty overlay."""
    return _CommittedCandidateRepository(store)


def candidate_with(
    base: CandidateRepository,
    *,
    changed_diagrams: tuple[DiagramRecord, ...] | list[DiagramRecord] = (),
    deleted_ids: frozenset[str] = frozenset(),
    workspace_types: dict[str, frozenset[str]] | None = None,
) -> CandidateRepository:
    """Build a CandidateRepository that applies changed_diagrams and deleted_ids over base.

    For each changed_diagram: the old diagram and all its base-view entity/connection children
    are suppressed; the new diagram and its re-extracted children are added.
    For each deleted_id naming a diagram: the diagram and all its children are suppressed.

    *workspace_types* maps diagram-type name → frozenset of workspace-scoped entity-type names.
    Callers in the infrastructure layer supply this; pass ``None`` to use no workspace scoping.
    """
    from src.application._diagram_entity_extraction import (  # noqa: PLC0415
        extract_diagram_connections,
        extract_diagram_entities,
    )

    ws_map = workspace_types or {}
    additions: dict[str, EntityRecord | ConnectionRecord | DiagramRecord] = {}
    suppressions: set[str] = set(deleted_ids)

    for did in list(deleted_ids):
        old_diag = base.get_diagram(did)
        if old_diag is not None:
            suppressions.update(_child_entity_ids(base, old_diag))

    for new_diag in changed_diagrams:
        old_diag = base.get_diagram(new_diag.artifact_id)
        suppressions.add(new_diag.artifact_id)
        if old_diag is not None:
            suppressions.update(_child_entity_ids(base, old_diag))
        ws = ws_map.get(new_diag.diagram_type, frozenset())
        additions[new_diag.artifact_id] = new_diag
        for e in extract_diagram_entities(new_diag, ws):
            additions[e.artifact_id] = e
        for c in extract_diagram_connections(new_diag, ws):
            additions[c.artifact_id] = c

    overlay = _Overlay(additions=additions, deletions=frozenset(suppressions))
    return _OverlayCandidateRepository(base, overlay)
