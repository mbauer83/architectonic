"""Application-level read-model DTOs shared across ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict, get_args

#: What a read's body is a function of, beyond the request's own arguments.
#:
#: Every cached read is a function of the indexed model. Two kinds are a function of something more,
#: which changes *without* the model changing — a scratchpad is not model content, and saving one
#: deliberately leaves the model's generation where it was, because a canvas saves about once a
#: second and would otherwise invalidate every model read in the product at that rate:
#:
#: * ``model+references`` — the body lists where an artifact is referred to, and a scratchpad note
#:   bound to it is one of the places. An entity's page showed a pad that had been deleted, and did
#:   not show one that had just bound it, for as long as the client kept revalidating.
#: * ``model+scratchpads`` — the body carries scratchpads or their notes themselves, as a search does.
#:
#: The first moves only when a reference list would read differently, so a canvas being typed into
#: does not disturb the entity pages; the second moves with every scratchpad save, and is carried
#: only by reads that would otherwise serve the save's own text stale.
ReadDependence = Literal["model", "model+references", "model+scratchpads"]


@dataclass(frozen=True)
class ReadModelVersion:
    """The read model's version, and the validator for each thing a read can depend on.

    ``generation`` and ``etag`` describe the model alone. The other two tags move whenever ``etag``
    does and also on their own, so a read validated by one can never be *less* fresh than the model.
    All four are required: a default would let a new index answer "the model's tag" for a read that
    depends on more, which is the stale 304 this exists to prevent.
    """

    generation: int
    etag: str
    references_etag: str
    scratchpads_etag: str

    def validator(self, dependence: ReadDependence) -> str:
        """The tag that stays the same exactly as long as a body with this dependence does."""
        match dependence:
            case "model":
                return self.etag
            case "model+references":
                return self.references_etag
            case "model+scratchpads":
                return self.scratchpads_etag


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
    specializations: list[str]
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
