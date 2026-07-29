"""Structural facts about an architecture element, computed from typed relationships only.

Counting edges is not analysis. This ontology declares, per relation type, a `derivation_role`
(`structural` / `dependency` / `dynamic` / `specialization`) and, for the two load-bearing roles, a
`derivation_strength` — composition 4, aggregation 3, assignment 2, realization 1; serving 4,
access 3, influence 2, association 1. Untyped degree throws all of that away: a component with
twenty associations and one with twenty compositions are not comparable, and a metric that says they
are is worse than no metric.

Three rules make a graph-derived value trustworthy, and all three are enforced here:

* **Typed only.** Every traversal filters by role and weights by declared strength. Association is
  excluded outright — it is the weakest dependency and asserts no direction of reliance, so
  counting it as a dependent manufactures a fact the model never stated.
* **Absent, not zero — with a completeness qualifier.** An element with no modelled neighbourhood
  yields *absence*. A zero would say "nothing depends on this", when the truth is "nobody has drawn
  what does". Each value reports how much of its neighbourhood is modelled, and one computed over a
  thin neighbourhood is marked provisional.
* **Witness-backed.** Every value carries the relationships that produced it. A number nobody can
  audit will not be trusted, and should not be.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import monotonic

from src.domain.artifact_id import canonical_entity_key
from src.domain.relationships.relationship_reachability import DerivationBounds

STRUCTURAL = "structural"
DEPENDENCY = "dependency"

#: The roles a reliance claim may be built from. Dynamic and specialization are excluded: a flow
#: says what moves, not what depends, and a specialization says what something *is*.
RELIANCE_ROLES: frozenset[str] = frozenset({STRUCTURAL, DEPENDENCY})

#: Excluded from every reliance traversal. The repository already documents why composing *through*
#: an association manufactures meaning the model never asserted; the same reasoning makes it unfit
#: to count as a dependency on its own.
EXCLUDED_CONNECTION_TYPE = "archimate-association"

#: Below this many typed relationships in an element's neighbourhood, a value stands but is reported
#: provisional: it is arithmetically correct and rests on very little.
THIN_NEIGHBOURHOOD = 3


@dataclass(frozen=True)
class TypedEdge:
    """One relationship, with the derivation metadata that makes it countable."""

    connection_id: str
    source_id: str
    target_id: str
    connection_type: str
    role: str | None
    strength: int | None


@dataclass(frozen=True)
class Reliance:
    """What leans on one element, and how heavily."""

    element_id: str
    dependent_ids: tuple[str, ...]
    weight: int
    """Summed declared strength of the counted relationships. A weight, not a score: it ranks
    elements against each other and is never presented as a rating."""
    witness: tuple[str, ...]
    provisional: bool

    @property
    def dependent_count(self) -> int:
        return len(self.dependent_ids)


def countable(edge: TypedEdge) -> bool:
    """Whether a relationship may be counted as a reliance at all."""
    return (
        edge.role in RELIANCE_ROLES
        and edge.strength is not None
        and edge.connection_type != EXCLUDED_CONNECTION_TYPE
    )


def typed_edges(
    connections: Sequence[Mapping[str, object]],
    connection_types: Mapping[str, object],
) -> tuple[TypedEdge, ...]:
    """Pair each connection with its declared role and strength, once per run.

    Endpoints are canonicalised here, at the one place connection records become this graph, so
    every value derived from it is keyed the same way. Both forms of an entity id reach this
    boundary — a connection may record either — and everything downstream matches by equality:
    unnormalised, one element becomes two nodes that neither depend on each other nor share a
    dependent, which is precisely the shape a single point of failure is *not*.
    """
    built: list[TypedEdge] = []
    for connection in connections:
        info = connection_types.get(str(connection.get("connection_type", "")))
        built.append(TypedEdge(
            connection_id=str(connection.get("artifact_id", "")),
            source_id=canonical_entity_key(str(connection.get("source", ""))),
            target_id=canonical_entity_key(str(connection.get("target", ""))),
            connection_type=str(connection.get("connection_type", "")),
            role=getattr(info, "derivation_role", None),
            strength=getattr(info, "derivation_strength", None),
        ))
    return tuple(built)


def reliance_on(element_id: str, edges: Sequence[TypedEdge]) -> Reliance | None:
    """What depends on `element_id`, or None when nothing about it is modelled.

    A dependent is the *source* of a countable relationship pointing at this element: serving,
    access, composition and their kin all read "the source leans on the target".
    """
    neighbourhood = [e for e in edges if element_id in (e.source_id, e.target_id)]
    if not neighbourhood:
        return None
    counted = [e for e in neighbourhood if e.target_id == element_id and countable(e)]
    return Reliance(
        element_id=element_id,
        dependent_ids=tuple(sorted({e.source_id for e in counted})),
        weight=sum(e.strength or 0 for e in counted),
        witness=tuple(
            f"{e.source_id} --{e.connection_type}({e.strength})--> {element_id}"
            for e in sorted(counted, key=lambda e: (e.source_id, e.connection_type))
        ),
        provisional=len(neighbourhood) < THIN_NEIGHBOURHOOD,
    )


def sole_providers(edges: Sequence[TypedEdge]) -> dict[str, tuple[str, ...]]:
    """Elements that are the only thing a dependent relies on, mapped to those dependents.

    An element nothing can stand in for. This is what a failure-mode analysis is *for*, and here it
    is exact rather than remembered — the dependent's own reliance set is what decides it, so an
    element with one dependent that also relies on two alternatives is not a sole provider.
    """
    provides: dict[str, set[str]] = {}
    for edge in edges:
        if countable(edge):
            provides.setdefault(edge.source_id, set()).add(edge.target_id)
    sole: dict[str, set[str]] = {}
    for dependent, providers in provides.items():
        if len(providers) == 1:
            sole.setdefault(next(iter(providers)), set()).add(dependent)
    return {element: tuple(sorted(dependents)) for element, dependents in sorted(sole.items())}


#: The budget a reliance walk runs under when a caller states none. Deliberately the derivation
#: engine's own defaults rather than a second set of numbers: these walks answer different questions
#: from the engine, but they run over the same graph and must be bounded the same way, or one
#: sparsely-modelled corner makes an entity page slow with nothing to stop it.
DEFAULT_BOUNDS = DerivationBounds(max_hops=4, max_relationships=20000, time_budget_seconds=2.0)


def _outgoing(edges: Sequence[TypedEdge]) -> dict[str, list[str]]:
    """Adjacency over countable relations, built once per call rather than per anchor."""
    out: dict[str, list[str]] = {}
    for edge in edges:
        if countable(edge):
            out.setdefault(edge.source_id, []).append(edge.target_id)
    return out


def _reached(
    start: str,
    outgoing: Mapping[str, list[str]],
    *,
    bounds: DerivationBounds,
    deadline: float,
) -> tuple[dict[str, int], bool]:
    """Everything `start` transitively relies on, with the hop it was first reached at.

    Returns the reach and whether a budget stopped the walk. A truncated reach is reported rather
    than silently returned short: a shared dependency the walk did not get to is exactly the
    finding this exists to surface, and "found nothing" must not stand in for "stopped looking".
    """
    reached: dict[str, int] = {}
    frontier = [start]
    for hop in range(1, bounds.max_hops + 1):
        next_frontier: list[str] = []
        for node in frontier:
            if monotonic() > deadline:
                return reached, True
            for target in outgoing.get(node, []):
                if target == start or target in reached:
                    continue
                if len(reached) >= bounds.max_relationships:
                    return reached, True
                reached[target] = hop
                next_frontier.append(target)
        frontier = next_frontier
        if not frontier:
            # Nothing further to explore: the walk is complete, not cut short.
            return reached, False
    # The hop budget ran out with somewhere still to go. That is truncation just as surely as the
    # time or relationship ceiling, and reporting it is the difference between "nothing shared" and
    # "stopped before finding out".
    return reached, bool(frontier)


@dataclass(frozen=True)
class CommonCause:
    """Two elements that stand as each other's alternative but share something underneath."""

    left_id: str
    right_id: str
    shared_ancestor_id: str
    left_witness: tuple[str, ...]
    right_witness: tuple[str, ...]
    provisional: bool = False
    """True when a budget stopped one of the two walks, so the pair may share more than is listed."""


@dataclass(frozen=True)
class CommonCauseReport:
    """What the pair walk found, and whether it ran to completion."""

    exposures: tuple[CommonCause, ...]
    truncated: bool
    """True when a budget stopped a walk. An absent finding is then "not looked for", not "absent" —
    the distinction every other absence in this feature is careful to keep."""


def common_cause_report(
    pairs: Sequence[tuple[str, str]],
    edges: Sequence[TypedEdge],
    *,
    bounds: DerivationBounds = DEFAULT_BOUNDS,
) -> CommonCauseReport:
    """Pairs that are redundant on paper but share a transitive dependency.

    The blind spot of both methods: two elements standing in for each other are not redundant at all
    if the same host, store or library sits under both. Neither a control-structure analysis (which
    looks at control, not duplication) nor a per-component worksheet (which looks at one row at a
    time) finds this, because it is a property of a *pair*.

    Redundancy is never declared, only discovered — the candidate pairs come from the graph showing
    two elements serving the same dependents, so there is no declared attribute to contradict.
    """
    outgoing = _outgoing(edges)
    deadline = monotonic() + bounds.time_budget_seconds
    found: list[CommonCause] = []
    truncated = False
    for left, right in pairs:
        left_reach, left_cut = _reached(left, outgoing, bounds=bounds, deadline=deadline)
        right_reach, right_cut = _reached(right, outgoing, bounds=bounds, deadline=deadline)
        cut = left_cut or right_cut
        truncated = truncated or cut
        for ancestor in sorted(set(left_reach) & set(right_reach)):
            found.append(CommonCause(
                left_id=left,
                right_id=right,
                shared_ancestor_id=ancestor,
                left_witness=(f"{left} relies on {ancestor} within {left_reach[ancestor]} hop(s)",),
                right_witness=(f"{right} relies on {ancestor} within {right_reach[ancestor]} hop(s)",),
                provisional=cut,
            ))
    return CommonCauseReport(exposures=tuple(found), truncated=truncated)


def common_cause_exposure(
    pairs: Sequence[tuple[str, str]],
    edges: Sequence[TypedEdge],
    *,
    bounds: DerivationBounds = DEFAULT_BOUNDS,
) -> tuple[CommonCause, ...]:
    """The exposures alone, for callers that do not surface truncation."""
    return common_cause_report(pairs, edges, bounds=bounds).exposures


def interchangeable_pairs(edges: Sequence[TypedEdge]) -> tuple[tuple[str, str], ...]:
    """Element pairs the graph shows serving the same dependent — candidate stand-ins.

    Discovered rather than declared: a declaration reading `active-active` while the model shows one
    provider would be a second source of truth, and the graph is the one that knows.
    """
    provides: dict[str, set[str]] = {}
    for edge in edges:
        if countable(edge):
            provides.setdefault(edge.source_id, set()).add(edge.target_id)
    pairs: set[tuple[str, str]] = set()
    for providers in provides.values():
        ordered = sorted(providers)
        pairs.update(
            (ordered[i], ordered[j])
            for i in range(len(ordered))
            for j in range(i + 1, len(ordered))
        )
    return tuple(sorted(pairs))
