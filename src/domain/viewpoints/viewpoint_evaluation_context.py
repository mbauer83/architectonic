"""Shared context types for the pure criteria evaluator: the
read-access surface it needs for adjacency/endpoint lookups, and the outcome shape every
evaluation function returns.

``CriteriaReadAccess`` is deliberately narrow and structurally identical to the relevant
slice of the existing ``ArtifactLookup``/``RelationshipGraph`` application ports
(``src/application/ports.py``) — any real artifact store already satisfies it, so no new
port or adapter is needed to wire a live evaluator, per the standing "use existing read
ports" rule. Direction filtering is always done by the evaluator itself (symmetric-type
normalization lives in ``viewpoint_criteria_evaluation.py``), so callers only ever pass
``direction="any"`` here and let the evaluator narrow further.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot


class CriteriaReadAccess(Protocol):
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]: ...


@dataclass(frozen=True)
class EvaluationOutcome:
    """Result of evaluating one criteria (sub)tree: the match/no-match verdict plus any
    schema-drift attribute paths encountered anywhere in the subtree. Drift is collected from
    every branch regardless of which one decided the match — evaluation never short-circuits
    away a warning."""

    matched: bool
    schema_drift: frozenset[str] = frozenset()
    inactive: bool = False
    """True when this (sub)tree asserts NOTHING because it rests on a declared-optional
    parameter the caller did not supply — a term to be REMOVED from its conjunction rather
    than a failed match. Removing it reduces the group to its identity (``and`` → match,
    ``or`` → no-match), which is exactly "this filter was not applied"; treating it as a
    non-match would instead make an unset optional filter silently exclude everything.

    Reserved for that one legitimate case. A reference that is BROKEN (an unknown type, a
    deleted entity) must NEVER be inactive: dropping it would silently WIDEN results, hiding
    the breakage. Broken references keep failing to match and are reported."""
    derived_evidence_hops: int | None = None
    """Set iff this outcome is a match that REQUIRED derived-relationship evidence: the
    minimum witness-chain length among the derived incident matches the verdict rests on.
    ``None`` for non-matches, for matches establishable from direct/modeled facts alone,
    and for negated (sub)trees — a negation's match asserts absence, not derived presence.
    Surfaces let users distinguish "matched via a modeled connection" from "matched via a
    derived one" without re-deriving anything."""


@dataclass(frozen=True)
class EvaluationEnvironment:
    """Execution-local values made available to criteria evaluation."""

    bindings: Mapping[str, object] = field(default_factory=dict)
    parameters: Mapping[str, object] = field(default_factory=dict)
    derived_values: Mapping[tuple[str, str], object] = field(default_factory=dict)
    inactive_parameters: frozenset[str] = frozenset()
    """Names that are DECLARED, optional, and unsupplied for this execution — conditions
    referencing them evaluate to ``inactive`` and drop out of their conjunction.

    Deliberately a separate set from ``parameters`` rather than a ``None`` value: a name
    absent from BOTH maps is an unknown reference (an authoring typo), which must keep
    failing to match instead of silently removing a filter."""


@dataclass(frozen=True)
class BindingEvaluationInput:
    """The scope-partitioned candidate ids plus read access/registries every binding and
    derived-attribute evaluator needs — resolved once by the application layer and shared
    across primary matching, all bindings, and all derived attributes in one execution."""

    entity_ids: tuple[str, ...]
    connection_ids: tuple[str, ...]
    read_access: CriteriaReadAccess
    registries: RegistrySnapshot
