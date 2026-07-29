"""viewpoint-execution/v1 strategy: turns a viewpoint execution into a persistent,
refreshable view-derivation candidate set. Modeled connections flow through by id;
derived connections are never turned into synthetic connection ids (the standing
"derived relationships are never persisted" invariant) — they flow through as candidate
witness paths, the same channel ``path-projection`` already uses.

Pure application logic only: ``catalog``/``read_access``/``registries`` are injected by
the composition-root registration closure (``src.infrastructure.derivation_strategy_wiring``),
which is the only layer allowed to build them from the strategy parameters' ``repo_roots``
(a ``ModelQuery``-only ``derive_fn`` cannot reach a ``ViewpointCatalog`` or ``RegistrySnapshot``
itself — both require real repo-root paths ``ModelQuery`` never carries).
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.derivation.types import CandidateSet
from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.execution_result import ViewpointExecutionResult
from src.application.viewpoints.ports import RepositoryReadAccess
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.viewpoints.view_derivations import DerivationSelection, PathProvenance
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoints import ViewpointCatalog

SPEC = StrategySpec(name="viewpoint_execution", version=1, supported_filters=frozenset())


def _build_request(params: Mapping[str, object]) -> ViewpointExecutionRequest:
    slug = params.get("slug")
    raw_query = params.get("query")
    raw_parameters = params.get("parameters")
    return ViewpointExecutionRequest(
        slug=str(slug) if isinstance(slug, str) else None,
        query=query_from_mapping(raw_query, label="query") if isinstance(raw_query, Mapping) else None,
        parameters=raw_parameters if isinstance(raw_parameters, Mapping) else None,
    )


def _path_key(synthetic_connection_id: str) -> str:
    """Recover the canonical witness-path key from a derived connection's synthetic id
    (``derived::<type-slug>::<path-key>``, per the relationship-derivation engine)."""
    return synthetic_connection_id.split("::", 2)[2]


def _evaluate(
    params: Mapping[str, object],
    *,
    catalog: ViewpointCatalog,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
    max_entities: int,
    default_limit: int,
    timeout_seconds: float,
) -> ViewpointExecutionResult:
    return evaluate_viewpoint(
        _build_request(params),
        catalog=catalog,
        read_access=read_access,
        registries=registries,
        index_generation=None,
        max_entities=max_entities,
        default_limit=default_limit,
        timeout_seconds=timeout_seconds,
    )


def evaluate_candidates(
    params: Mapping[str, object],
    *,
    catalog: ViewpointCatalog,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
    max_entities: int,
    default_limit: int,
    timeout_seconds: float,
) -> CandidateSet:
    result = _evaluate(
        params,
        catalog=catalog,
        read_access=read_access,
        registries=registries,
        max_entities=max_entities,
        default_limit=default_limit,
        timeout_seconds=timeout_seconds,
    )
    modeled_connection_ids = frozenset(cid for cid in result.connection_ids if not cid.startswith("derived::"))
    paths = frozenset(_path_key(summary.id) for summary in result.connections if summary.certainty is not None)
    return CandidateSet(entity_ids=frozenset(result.entity_ids), connection_ids=modeled_connection_ids, paths=paths)


def default_selection(
    params: Mapping[str, object],
    *,
    catalog: ViewpointCatalog,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
    max_entities: int,
    default_limit: int,
    timeout_seconds: float,
) -> DerivationSelection:
    """Initial acceptance state for a freshly generated diagram: certain
    derived candidates pre-included, potential ones pre-excluded until explicitly
    accepted. Modeled entities/connections carry no certainty ambiguity, so they are
    simply part of the generated result."""
    result = _evaluate(
        params,
        catalog=catalog,
        read_access=read_access,
        registries=registries,
        max_entities=max_entities,
        default_limit=default_limit,
        timeout_seconds=timeout_seconds,
    )
    modeled_connection_ids = sorted(cid for cid in result.connection_ids if not cid.startswith("derived::"))
    included_paths: list[str] = []
    excluded_paths: list[str] = []
    provenance: dict[str, PathProvenance] = {}
    for summary in result.connections:
        if summary.certainty is None:
            continue
        path_key = _path_key(summary.id)
        (included_paths if summary.certainty == "certain" else excluded_paths).append(path_key)
        provenance[path_key] = PathProvenance(certainty=summary.certainty, connection_type=summary.type)
    included_paths.sort()
    excluded_paths.sort()
    return DerivationSelection(
        included_entity_ids=tuple(sorted(result.entity_ids)),
        included_connection_ids=tuple(modeled_connection_ids),
        included_paths=tuple(included_paths),
        excluded_paths=tuple(excluded_paths),
        path_provenance=provenance,
    )
