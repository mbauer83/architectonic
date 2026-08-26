"""Composition-root wiring for derivation strategies whose ``derive_fn`` needs more than
the bare ``ModelQuery``/``SourceModelSnapshot`` a strategy normally sees:

- ``viewpoint_execution`` needs a ``ViewpointCatalog`` and a ``RegistrySnapshot``, both
  built from real repo-root paths. Those roots travel as plain data in the strategy's own
  ``params["repo_roots"]`` (set at generation time), never through the shared
  ``ModelQuery``/``DeriveFn`` contract every other strategy also implements against.
- ``derived_relationships`` needs the ontology ``ModuleCatalog`` the relationship-
  derivation engine reads its rule tables from — roots-independent, so no ``params`` data
  is needed, but its construction still lives at the composition root.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.repository import ArtifactRepository
from src.application.derivation.derived_relationships import evaluate_candidates as derive_relationship_candidates
from src.application.derivation.types import CandidateSet, ModelQuery
from src.application.derivation.viewpoint_execution import evaluate_candidates
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_execution_default_entity_limit_mcp,
    viewpoints_execution_max_entities,
    viewpoints_execution_timeout_seconds,
)
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.viewpoint_declarations import load_effective_viewpoint_catalog
from src.infrastructure.viewpoints_snapshot import configured_registry_snapshot


def _repo_roots(params: dict[str, object]) -> list[Path]:
    raw = params.get("repo_roots")
    return [Path(str(root)) for root in raw] if isinstance(raw, list) else []


def viewpoint_execution_derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    roots = _repo_roots(params)
    read_access = ArtifactRepository(shared_artifact_index(roots))
    runtime_catalogs = process_runtime_catalogs()
    return evaluate_candidates(
        params,
        catalog=load_effective_viewpoint_catalog(roots),
        read_access=read_access,
        registries=configured_registry_snapshot(runtime_catalogs, roots),
        max_entities=viewpoints_execution_max_entities(),
        default_limit=viewpoints_execution_default_entity_limit_mcp(),
        timeout_seconds=viewpoints_execution_timeout_seconds(),
    )


def derived_relationships_derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    return derive_relationship_candidates(
        params,
        read_access=query,
        catalog=process_runtime_catalogs().module_catalog,
        default_max_hops=viewpoints_derivation_max_hops(),
        max_relationships=viewpoints_derivation_max_relationships(),
    )
