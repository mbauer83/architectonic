"""AIBOM derivation core — the differentiator.

A PURE projection: AI-specialized entities + connections + resolved role bindings → a typed
AIBOM component set, each field marked derived-from-relationships or authored-on-the-entity,
with authored winning (D5). No IO, no store access, no HTTP — everything comes in as
arguments so the whole engine is unit-testable in isolation.

Datasets come from the ``trained-on`` / ``evaluated-on`` / ``fine-tuned-from`` role
bindings; governance from the ``governed-by`` binding; the BOM dependency graph from
connections between two AI components. What the entity authored (its Properties, already
decoded onto ``EntityRecord.attributes``) is carried verbatim and overrides any derived
value for the same field.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from src.domain.artifact_id import stable_id
from src.domain.assurance.aibom_roles import DerivationRoleBindings
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

Provenance = Literal["derived", "authored"]

#: The AIBOM's own vocabulary: each AI specialization → its CycloneDX component ``type``. The
#: keys are the set of specializations that make an entity an AI component. Kept here because
#: mapping an architecture specialization to a BOM component type is the exporter's knowledge;
#: a drift test pins it against the shipped ontology so a renamed slug cannot go unnoticed.
AI_COMPONENT_TYPE: dict[str, str] = {
    "ai-model": "machine-learning-model",
    "ai-agent": "application",
    "ai-inference-service": "service",
    "ai-dataset": "data",
    "ai-prompt-asset": "data",
    "ai-vector-store": "data",
    "ai-runtime": "application",
    "ai-tool-interface": "library",
}

AI_SPECIALIZATIONS: frozenset[str] = frozenset(AI_COMPONENT_TYPE)

_DATASET_ROLES: tuple[str, ...] = ("trained-on", "evaluated-on", "fine-tuned-from")
_GOVERNANCE_ROLES: tuple[str, ...] = ("governed-by", "guarded-by")

#: Motivation entity types that populate the model card's ``considerations`` (B2). ``users``
#: are the stakeholders the AI serves; ``useCases`` the drivers/goals it addresses.
_USER_TYPES: frozenset[str] = frozenset({"stakeholder"})
_USE_CASE_TYPES: frozenset[str] = frozenset({"driver", "goal"})

#: Default reachability bound for the considerations walk — deep enough to cross an
#: application-to-motivation hop or two, shallow enough to stay a bound, not a graph sweep.
DEFAULT_CONSIDERATION_DEPTH = 3


@dataclass(frozen=True)
class ProvenancedValue:
    """One AIBOM field value tagged with where it came from."""

    value: Any
    provenance: Provenance


@dataclass(frozen=True)
class RoleMatch:
    """A connection that realised a derivation role: the role, and the target it reached."""

    role: str
    target_entity_id: str
    target_name: str
    target_specialization: str


@dataclass(frozen=True)
class MotivationRef:
    """A motivation entity reached from an AI component — a considerations ``user`` or
    ``useCase``."""

    entity_id: str
    name: str
    entity_type: str


@dataclass(frozen=True)
class Considerations:
    """The model card's derived considerations: who it serves and what it is for."""

    users: tuple[MotivationRef, ...] = ()
    use_cases: tuple[MotivationRef, ...] = ()


@dataclass(frozen=True)
class AibomComponent:
    """One derived AIBOM component. ``authored`` carries the model-card / supplier attributes
    the entity declared (each ``authored``); the relational fields are derived."""

    entity_id: str
    name: str
    specialization: str
    component_type: str
    authored: Mapping[str, ProvenancedValue] = field(default_factory=dict)
    datasets: tuple[RoleMatch, ...] = ()
    governance: tuple[RoleMatch, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    role_matches: tuple[RoleMatch, ...] = ()
    considerations: Considerations = field(default_factory=Considerations)


def ai_specialization_of(entity: EntityRecord) -> str | None:
    """The entity's AI specialization slug, or ``None`` if it carries none. The first AI
    specialization wins if (unusually) several are applied — a concept is one BOM component."""
    return next((slug for slug in entity.specializations if slug in AI_SPECIALIZATIONS), None)


def derive_aibom(
    entities: Sequence[EntityRecord],
    connections: Sequence[ConnectionRecord],
    bindings: DerivationRoleBindings,
    *,
    consideration_depth: int = DEFAULT_CONSIDERATION_DEPTH,
) -> tuple[AibomComponent, ...]:
    """Project the AI-specialized entities into AIBOM components. ``entities`` is the full
    entity set (targets are resolved against it); only those carrying an AI specialization
    become components. Deterministic and total: an entity with no relations yields a valid,
    sparse component; cycles in the dependency graph terminate (each edge is emitted once,
    no traversal); considerations reachability is bounded by ``consideration_depth``."""
    by_short_id: dict[str, EntityRecord] = {stable_id(e.artifact_id): e for e in entities}
    ai_entities = [e for e in entities if ai_specialization_of(e) is not None]
    ai_short_ids = {stable_id(e.artifact_id) for e in ai_entities}
    outgoing = _connections_by_source(connections)
    adjacency = _undirected_adjacency(connections)

    components: list[AibomComponent] = []
    for entity in ai_entities:
        components.append(
            _derive_component(entity, by_short_id, ai_short_ids, outgoing, adjacency, bindings, consideration_depth)
        )
    return tuple(components)


def _derive_component(
    entity: EntityRecord,
    by_short_id: Mapping[str, EntityRecord],
    ai_short_ids: set[str],
    outgoing: Mapping[str, list[ConnectionRecord]],
    adjacency: Mapping[str, set[str]],
    bindings: DerivationRoleBindings,
    consideration_depth: int,
) -> AibomComponent:
    specialization = ai_specialization_of(entity)
    assert specialization is not None  # ai_entities filter guarantees it
    matches = _role_matches(entity, by_short_id, outgoing, bindings)
    dependency_ids = _dependency_ids(entity, by_short_id, ai_short_ids, outgoing)
    return AibomComponent(
        entity_id=entity.artifact_id,
        name=entity.name,
        specialization=specialization,
        component_type=AI_COMPONENT_TYPE[specialization],
        authored=_authored_attributes(entity),
        datasets=tuple(m for m in matches if m.role in _DATASET_ROLES),
        governance=tuple(m for m in matches if m.role in _GOVERNANCE_ROLES),
        dependency_ids=dependency_ids,
        role_matches=matches,
        considerations=_considerations(entity, by_short_id, adjacency, consideration_depth),
    )


def _considerations(
    entity: EntityRecord,
    by_short_id: Mapping[str, EntityRecord],
    adjacency: Mapping[str, set[str]],
    max_depth: int,
) -> Considerations:
    """Stakeholders (users) and drivers/goals (use cases) within ``max_depth`` connection
    hops of the AI component. A bounded BFS — never an unbounded graph walk; ``max_depth <= 0``
    reaches nothing but the component itself (no motivation)."""
    users: list[MotivationRef] = []
    use_cases: list[MotivationRef] = []
    start = stable_id(entity.artifact_id)
    visited = {start}
    frontier = [start]
    for _ in range(max(max_depth, 0)):
        nxt: list[str] = []
        for node in frontier:
            for neighbour in sorted(adjacency.get(node, set())):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                nxt.append(neighbour)
                target = by_short_id.get(neighbour)
                if target is None:
                    continue
                ref = MotivationRef(target.artifact_id, target.name, target.artifact_type)
                if target.artifact_type in _USER_TYPES:
                    users.append(ref)
                elif target.artifact_type in _USE_CASE_TYPES:
                    use_cases.append(ref)
        frontier = nxt
    return Considerations(users=tuple(users), use_cases=tuple(use_cases))


def _authored_attributes(entity: EntityRecord) -> dict[str, ProvenancedValue]:
    """Every non-empty decoded Property is an authored AIBOM field (D5: authored, and so it
    wins over any same-named derived value downstream)."""
    authored: dict[str, ProvenancedValue] = {}
    for key, value in entity.attributes.items():
        if value in (None, "", [], {}):
            continue
        authored[key] = ProvenancedValue(value=value, provenance="authored")
    return authored


def _role_matches(
    entity: EntityRecord,
    by_short_id: Mapping[str, EntityRecord],
    outgoing: Mapping[str, list[ConnectionRecord]],
    bindings: DerivationRoleBindings,
) -> tuple[RoleMatch, ...]:
    matches: list[RoleMatch] = []
    conns = outgoing.get(stable_id(entity.artifact_id), [])
    for role in sorted(bindings.bound_roles()):
        binding = bindings.get(role)
        if binding is None:
            continue
        for conn in conns:
            if conn.conn_type not in binding.connection_types:
                continue
            target = by_short_id.get(stable_id(conn.target))
            if target is None:
                continue
            target_spec = ai_specialization_of(target) or ""
            if binding.target_specializations and target_spec not in binding.target_specializations:
                continue
            matches.append(
                RoleMatch(
                    role=role,
                    target_entity_id=target.artifact_id,
                    target_name=target.name,
                    target_specialization=target_spec,
                )
            )
    return tuple(matches)


def _dependency_ids(
    entity: EntityRecord,
    by_short_id: Mapping[str, EntityRecord],
    ai_short_ids: set[str],
    outgoing: Mapping[str, list[ConnectionRecord]],
) -> tuple[str, ...]:
    """AI components this one connects to — the BOM ``dependencies[]`` edges. Emitted once per
    distinct target, in first-seen order; no graph walk, so cycles cannot loop."""
    seen: dict[str, None] = {}
    for conn in outgoing.get(stable_id(entity.artifact_id), []):
        target_short = stable_id(conn.target)
        if target_short in ai_short_ids and target_short != stable_id(entity.artifact_id):
            target = by_short_id.get(target_short)
            if target is not None and target.artifact_id not in seen:
                seen[target.artifact_id] = None
    return tuple(seen)


def _connections_by_source(connections: Sequence[ConnectionRecord]) -> dict[str, list[ConnectionRecord]]:
    index: dict[str, list[ConnectionRecord]] = {}
    for conn in connections:
        index.setdefault(stable_id(conn.source), []).append(conn)
    return index


def _undirected_adjacency(connections: Sequence[ConnectionRecord]) -> dict[str, set[str]]:
    """Both-directions adjacency by short id — reachability to motivation follows a relation
    regardless of which way it was drawn."""
    adjacency: dict[str, set[str]] = {}
    for conn in connections:
        src, tgt = stable_id(conn.source), stable_id(conn.target)
        adjacency.setdefault(src, set()).add(tgt)
        adjacency.setdefault(tgt, set()).add(src)
    return adjacency
