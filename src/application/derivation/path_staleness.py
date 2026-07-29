"""Reconstruction-based staleness classification for accepted witness paths.

Re-derives each accepted path fresh via the shared reconstruction logic and classifies
the outcome against what was recorded at acceptance time (``PathProvenance``): broken
(a connection in the chain no longer exists or has a missing/unknown endpoint),
no-longer-derives (the chain is structurally intact but no rule composes it anymore), or
drift (the chain still derives, but as a different certainty or connection type than
what was accepted) — never silently redrawn or dropped, per the standing "the architect
re-reviews" contract. A bare path-key set-membership check (whether the key still
appears in a freshly computed candidate set) cannot see drift at all: the path key only
names which connections form the chain, never the type/certainty the composition
resolves to, so reconstruction is the only way to detect it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.relationships.relationship_path_reconstruction import (
    BrokenRelationshipPath,
    DerivedPathRelationship,
    NoLongerDerivedRelationship,
    RelationshipPathReadAccess,
    derive_relationship_for_path,
)
from src.domain.viewpoints.view_derivations import DerivationSelection


@dataclass(frozen=True)
class PathStalenessReport:
    broken_paths: tuple[str, ...] = ()
    no_longer_derives_paths: tuple[str, ...] = ()
    drifted_paths: tuple[str, ...] = ()

    @property
    def stale_paths(self) -> frozenset[str]:
        return frozenset(self.broken_paths) | frozenset(self.no_longer_derives_paths) | frozenset(self.drifted_paths)


def classify_accepted_path_staleness(
    selection: DerivationSelection | None,
    *,
    read_access: RelationshipPathReadAccess,
    catalog: ModuleCatalog,
) -> PathStalenessReport:
    if selection is None or not selection.included_paths:
        return PathStalenessReport()
    broken: list[str] = []
    no_longer_derives: list[str] = []
    drifted: list[str] = []
    for path_key in selection.included_paths:
        outcome = derive_relationship_for_path(path_key, read_access=read_access, registries=catalog)
        if isinstance(outcome, BrokenRelationshipPath):
            broken.append(path_key)
        elif isinstance(outcome, NoLongerDerivedRelationship):
            no_longer_derives.append(path_key)
        elif isinstance(outcome, DerivedPathRelationship):
            provenance = selection.path_provenance.get(path_key)
            if provenance is not None and (
                provenance.certainty != outcome.certainty or provenance.connection_type != outcome.connection_type
            ):
                drifted.append(path_key)
    return PathStalenessReport(
        broken_paths=tuple(sorted(broken)),
        no_longer_derives_paths=tuple(sorted(no_longer_derives)),
        drifted_paths=tuple(sorted(drifted)),
    )
