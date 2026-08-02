"""Application-level read-model DTOs shared across ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict, get_args


@dataclass(frozen=True)
class ReadModelVersion:
    generation: int
    etag: str


#: Which way a connection runs relative to the entity being read.
#:
#: Named here because this is where the grouping is *produced*. The vocabulary was spelled as a
#: ``Literal`` in the REST contract and as a bare ``str`` in this model, which puts the closed set on
#: the delivery side of a boundary whose application side decides it — so the delivery layer's
#: precision was a claim about someone else's data rather than a property of it.
ConnectionDirection = Literal["outbound", "inbound", "symmetric"]

#: The three directions, for a producer that has to validate a stored bucket name against them.
CONNECTION_DIRECTIONS: frozenset[str] = frozenset(get_args(ConnectionDirection))


class EntityContextConnection(TypedDict):
    artifact_id: str
    source: str
    target: str
    conn_type: str
    version: str
    status: str
    path: str
    content_text: str
    associated_entities: list[str]
    src_multiplicity: str
    tgt_multiplicity: str
    specialization: str
    source_name: str
    target_name: str
    source_artifact_type: str
    target_artifact_type: str
    source_domain: str
    target_domain: str
    source_scope: str
    target_scope: str
    other_entity_id: str
    direction: ConnectionDirection


class EntityContextConnections(TypedDict):
    """One entity's connections grouped by direction — three keys, always all three.

    A closed shape rather than ``dict[str, list[...]]``. The producer has always emitted exactly
    these three, and a symmetric relation belongs to neither direction, which is *why* they are
    grouped instead of flattened — so the key set is a decision, not a runtime accident. Typed as an
    open map it reached the published document as ``{[key: string]: ContextConnection[]}``: a client
    could not know which keys to read, and the frontend's decoder, which names all three and no
    others, could not be held against it.
    """

    outbound: list[EntityContextConnection]
    inbound: list[EntityContextConnection]
    symmetric: list[EntityContextConnection]


class EntityContextCounts(TypedDict):
    conn_in: int
    conn_out: int
    conn_sym: int


class EntityContextReadModel(TypedDict):
    entity: dict[str, Any]
    connections: EntityContextConnections
    counts: EntityContextCounts
    generation: int
    etag: str
