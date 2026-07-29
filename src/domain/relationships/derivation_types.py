"""Pure domain types for view derivation strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.view_derivations import SourceModelSnapshot


@dataclass(frozen=True)
class StrategySpec:
    name: str
    version: int
    supported_filters: frozenset[str]


@dataclass(frozen=True)
class CandidateSet:
    """Output of a derivation strategy: sets of model entity/connection artifact_ids.

    path-projection adds ``paths`` — a frozenset of canonical path keys
    (format: ``id1@fwd|id2@rev|...``) representing ordered connection paths.
    """

    entity_ids: frozenset[str] = field(default_factory=frozenset)
    connection_ids: frozenset[str] = field(default_factory=frozenset)
    paths: frozenset[str] = field(default_factory=frozenset)


class ModelQuery(Protocol):
    """Minimal read surface over the artifact index consumed by derivation strategies."""

    def entity_ids(self) -> set[str]: ...

    def connection_ids(self) -> set[str]: ...

    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]: ...


DeriveFn = Callable[[dict[str, object], SourceModelSnapshot, ModelQuery], CandidateSet]
