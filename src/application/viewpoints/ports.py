"""Narrow read port for the repository-context projection: the pure
criteria-evaluator's ``CriteriaReadAccess`` plus repo-scope-partitioned entity enumeration
and connection point-lookup (the execution result needs full ``ConnectionRecord``s
for its per-item summaries, not just ids).

Structurally identical to the matching slice of ``ArtifactIndexLifecycle``/``ArtifactLookup``
(``src/application/ports.py``) — the real artifact index and the verifier's
``ArtifactRegistry`` already satisfy this, so no new adapter is needed, per the standing
"use existing read ports" rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess


class RepositoryReadAccess(CriteriaReadAccess, Protocol):
    def entity_ids(self) -> set[str]: ...
    def enterprise_entity_ids(self) -> set[str]: ...
    def engagement_entity_ids(self) -> set[str]: ...
    def connection_ids(self) -> set[str]: ...
    def enterprise_connection_ids(self) -> set[str]: ...
    def engagement_connection_ids(self) -> set[str]: ...
    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...

@dataclass(frozen=True)
class SignalBasisSnapshot:
    """Provenance of one anchor's contribution to a batch."""

    anchor_entity_id: str
    snapshot_id: str
    activated_at: str


@dataclass(frozen=True)
class SignalMetricsBatch:
    """One batched fetch of signal-derived attribute values.

    ``values`` is keyed by (entity_id, metric_name). ``available=False`` means
    the whole batch is unusable (locked store, no active snapshot coherence, snapshot
    change mid-read) — callers fall back to unresolved-reference styling and
    surface ``note`` as the legend explanation; values are never mixed across
    snapshots. ``classification`` is the maximum TLP of the VISIBLE contributing
    records (computed, never hardcoded) and ``basis_snapshots`` the per-anchor
    provenance — the banner/export stamp reads both."""

    available: bool
    values: Mapping[tuple[str, str], object] = field(default_factory=dict)
    note: str | None = None
    classification: str | None = None
    basis_snapshots: tuple[SignalBasisSnapshot, ...] = ()


class SignalAttributeCapability(Protocol):
    """Batched external-attribute source for viewpoint evaluation (one call per
    execution phase — never per entity or per metric)."""

    def fetch_metrics(
        self, entity_ids: Sequence[str], metric_names: Sequence[str],
    ) -> SignalMetricsBatch: ...


class NullSignalAttributeCapability:
    """Composition-root default for deployments without the assurance
    capability — always unavailable, with a stable explanation."""

    def fetch_metrics(
        self, entity_ids: Sequence[str], metric_names: Sequence[str],
    ) -> SignalMetricsBatch:
        return SignalMetricsBatch(
            available=False,
            note="security signals are not configured in this deployment",
        )

