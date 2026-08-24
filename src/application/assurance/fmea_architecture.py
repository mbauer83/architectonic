"""The public architecture model, in the shape the failure-mode surfaces read it.

The method's structural half — which elements are load-bearing, what data a failure would touch,
which declared alternatives share a cause — is a statement about the architecture graph, not about
the assurance store. The store cannot answer any of it, so a surface that only reads the store
shows the analyst's own bindings and nothing the model knows.

This reads *public* model content into a confidential computation. The confidentiality direction is
never reversed: nothing here writes, and no assurance content crosses back into the architecture
repository. It is deliberately a read of records, assembled once per request, because the graph
metrics below are whole-graph questions and answering them per element would re-read the model for
every row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.fmea_structural_signals import TypedEdge, typed_edges
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import CONTAINMENT_KIND, ConnectionTypeInfo

CONNECTION_TYPE_KEY = "connection_type"


@runtime_checkable
class ArchitectureModelSource(Protocol):
    """The architecture repository, narrowed to the two reads this needs.

    Narrow on purpose: stated as the whole repository interface, every caller would have to supply
    a full repository to compute one graph metric, and a test would have to fake reads that play no
    part in the answer.
    """

    def list_entities(self) -> list[EntityRecord]: ...

    def list_connections(self) -> list[ConnectionRecord]: ...


@runtime_checkable
class ConnectionTypeSource(Protocol):
    """Where a connection type's derivation role and strength come from."""

    def all_connection_types(self) -> Mapping[str, ConnectionTypeInfo]: ...


@runtime_checkable
class EntityTypeSource(Protocol):
    """Which entity types denote something that acts.

    One question, answered by the ontology that owns the vocabulary — see
    `domain.ontology_representation.behavioral_elements`. A failure mode enumerates ways something
    malfunctions, so it is only a sensible question about an element that does something; a goal does
    not fail, it is met or missed.

    Deliberately *not* a list of type names or ArchiMate classes here. Both were, briefly, and that
    put one module's vocabulary inside another's: the ontology states which of its types act, and this
    layer asks. A newly declared component type is then covered without an edit anywhere.
    """

    def behavioral_entity_types(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class ArchitectureBasis:
    """One assembled view of the architecture graph, shared by every row in a request.

    The empty default is what a caller with no architecture model available gets, and it is
    honest rather than convenient: it yields no structural candidates and no cited facts, which is
    exactly the answer when the graph is unknown.
    """

    edges: tuple[TypedEdge, ...] = ()
    connections: tuple[Mapping[str, object], ...] = ()
    entities: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    containment_types: frozenset[str] = frozenset()
    """Which relation types mean one element contains another, from the ontology that declares it.

    Injected rather than named here: the ArchiMate module marks composition and aggregation
    `relationship_kind: containment`, and a layer that spelled those type names would be reading
    another module's vocabulary. Empty where no connection-type source was given, and an empty set
    expands nothing rather than guessing."""
    assembled: bool = False
    """Whether the graph was read at all, as against read and found to say nothing.

    The difference decides whether a judgement may be recorded: a basis that cites no facts about an
    element is something to hold a judgement against, and a basis nobody could assemble is not. Both
    are otherwise the same empty object, which is how eleven judgements came to be recorded against
    the second and retire the instant anyone read them with the model in hand."""
    analysable_element_ids: frozenset[str] = frozenset()
    """Elements a failure mode is a sensible question about — see
    `fmea_analysable_elements.can_bear_failure_modes`. Empty when no entity-type source was given,
    which is honest: without the ontology nothing here knows what kind of thing an element is."""


def _connection_mapping(record: ConnectionRecord) -> Mapping[str, object]:
    """A connection in the key shape the assurance side reads.

    `ConnectionRecord` names the type `conn_type`; every assurance consumer reads
    `connection_type`, matching the store's own rows. Translated here, at the one boundary where
    architecture records become assurance inputs, rather than at each reader.

    Endpoints are canonicalised at the same boundary, because `typed_edges` canonicalises its own
    and every downstream reader matches element ids by equality. Left raw, a connection recorded
    with the slugged form of an id would describe a different element than the graph metrics do,
    and a classification read would find nothing for an element that plainly accesses data.
    """
    return {
        "artifact_id": record.artifact_id,
        "source": canonical_entity_key(record.source),
        "target": canonical_entity_key(record.target),
        CONNECTION_TYPE_KEY: record.conn_type,
    }


def _entity_mapping(record: EntityRecord) -> Mapping[str, object]:
    """An entity's declared attributes, its type, and how it is named.

    The type and attributes are what a classification read needs. The name is what a *reader* needs:
    a matrix row keyed by element showed the bare artifact id, which is the one label that tells an
    analyst nothing about which element they are being asked to assess. It comes from here rather
    than from a second lookup at the row, because this is the one place the assurance surfaces
    obtain the architecture graph — a row resolving its own name would be a second source for it.

    The explicit keys are written after the spread so a declared attribute called `name` cannot
    shadow the entity's own.
    """
    return {
        **dict(record.attributes),
        "artifact_type": record.artifact_type,
        "name": record.name,
        "display_label": record.display_label,
    }


def read_architecture_basis(
    model: ArchitectureModelSource | None,
    *,
    connection_types: ConnectionTypeSource | None = None,
    entity_types: EntityTypeSource | None = None,
) -> ArchitectureBasis:
    """Assemble the graph once.

    `model` and `connection_types` are optional and a missing one yields the empty basis, because the
    failure-mode surfaces must stay usable where the architecture model is not reachable — the MCP
    server run standalone, or a test staging only a store. `entity_types` is optional for the same
    reason, and its absence narrows nothing rather than excluding everything: a caller that cannot say
    what kind of thing an element is gets an empty analysable set, and the checks that need it say so.
    """
    if model is None or connection_types is None:
        return ArchitectureBasis()
    connections = tuple(_connection_mapping(c) for c in model.list_connections())
    entities = {
        canonical_entity_key(e.artifact_id): _entity_mapping(e) for e in model.list_entities()
    }
    return ArchitectureBasis(
        edges=typed_edges(connections, dict(connection_types.all_connection_types())),
        connections=connections,
        entities=entities,
        containment_types=_containment_types(connection_types),
        assembled=True,
        analysable_element_ids=_analysable_ids(entities, entity_types),
    )


def _containment_types(connection_types: ConnectionTypeSource) -> frozenset[str]:
    """The relation types whose declared kind is containment.

    Read off the same `all_connection_types()` mapping the derivation roles come from, so no new port
    is needed and no ontology's type names are spelled here.
    """
    return frozenset(
        name for name, info in connection_types.all_connection_types().items()
        if getattr(info, "relationship_kind", None) == CONTAINMENT_KIND
    )


def _analysable_ids(
    entities: Mapping[str, Mapping[str, object]],
    entity_types: EntityTypeSource | None,
) -> frozenset[str]:
    """The elements a failure mode is a sensible question about: the ones whose type acts."""
    if entity_types is None:
        return frozenset()
    behavioral = entity_types.behavioral_entity_types()
    return frozenset(
        element_id for element_id, entity in entities.items()
        if str(entity.get("artifact_type", "")) in behavioral
    )


def accessed_data_by_element(
    basis: ArchitectureBasis,
    *,
    access_connection_type: str,
) -> Mapping[str, tuple[str, ...]]:
    """Which data objects each element reaches, for the coverage checks that ask about data.

    Built once over all connections rather than filtered per element: the callers iterate every
    candidate, and a per-element scan would make one request pay for the connection list repeatedly.
    """
    reached: dict[str, list[str]] = {}
    for connection in basis.connections:
        if str(connection.get(CONNECTION_TYPE_KEY, "")) != access_connection_type:
            continue
        reached.setdefault(str(connection.get("source", "")), []).append(str(connection.get("target", "")))
    return {element: tuple(sorted(set(targets))) for element, targets in reached.items()}


def classifications(
    basis: ArchitectureBasis,
    *,
    attribute: str,
    classified_types: frozenset[str],
) -> Mapping[str, str]:
    """The declared classification of every entity that is the kind of thing that carries one.

    Entities of other types are omitted rather than recorded as unclassified, so a coverage check
    cannot report an application component as data nobody classified.
    """
    return {
        entity_id: str(attributes.get(attribute) or "").strip()
        for entity_id, attributes in basis.entities.items()
        if str(attributes.get("artifact_type", "")) in classified_types
    }
