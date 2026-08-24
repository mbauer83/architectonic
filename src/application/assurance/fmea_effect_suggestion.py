"""Suggesting which hazard a failure mode's effect is likely to be.

Linking the effect is the analyst's most expensive step, because it means knowing which hazard this
particular component's failure ends up in — and that is a question about the architecture, not about
the component. The graph already knows which hazard-implicated elements this one serves or realizes,
so the search can be done for them.

**A suggestion, never an auto-link.** The causal claim stays human: whether *this* failure produces
*that* hazard is a judgement, and a system that quietly made it would be manufacturing the chain the
whole analysis rests on. What is automated is the search, ranked by typed path strength, with the
path shown so the analyst can see why each candidate is offered and reject it on sight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.assurance_node_types import CONTROL_STRUCTURE_NODE
from src.domain.assurance.fmea_structural_signals import TypedEdge, countable

BINDS_TO = "binds-to"
FAILURE_MODE = "failure-mode"
LEADS_TO = "leads-to"

#: How far to look for a hazard-implicated neighbour. Beyond this the connection is too indirect to
#: read as "this component's failure ends up there", and the suggestion list stops being a shortlist.
DEFAULT_MAX_HOPS = 3


@dataclass(frozen=True)
class EffectSuggestion:
    """One hazard this failure mode's effect might be, and the reason it is offered."""

    hazard_id: str
    hazard_name: str
    via_element_id: str
    strength: int
    """Summed declared strength along the path. Ranks suggestions against each other; it is not
    a confidence, and nothing decides anything from it."""
    hops: int
    witness: tuple[str, ...]


def _reachable(start: str, edges: Sequence[TypedEdge], *, max_hops: int) -> dict[str, tuple[int, int, tuple[str, ...]]]:
    """Elements `start` transitively relies on: hops, summed strength, and the path taken."""
    outgoing: dict[str, list[TypedEdge]] = {}
    for edge in edges:
        if countable(edge):
            outgoing.setdefault(edge.source_id, []).append(edge)
    best: dict[str, tuple[int, int, tuple[str, ...]]] = {}
    frontier: list[tuple[str, int, tuple[str, ...]]] = [(start, 0, ())]
    for hop in range(1, max_hops + 1):
        next_frontier: list[tuple[str, int, tuple[str, ...]]] = []
        for node, strength, path in frontier:
            for edge in outgoing.get(node, []):
                target = edge.target_id
                if target == start or target in best:
                    continue
                step = f"{edge.source_id} --{edge.connection_type}({edge.strength})--> {target}"
                total = strength + (edge.strength or 0)
                best[target] = (hop, total, (*path, step))
                next_frontier.append((target, total, (*path, step)))
        frontier = next_frontier
        if not frontier:
            break
    return best


def _control_nodes_by_element(
    arch_refs: Sequence[Mapping[str, object]],
    node_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for ref in arch_refs:
        if str(ref.get("ref_type")) != BINDS_TO:
            continue
        node = node_by_id.get(str(ref["assurance_node_id"]))
        if node is not None and str(node.get("node_type", "")) == CONTROL_STRUCTURE_NODE:
            # Stable form, to meet the graph ids this map is looked up by.
            element_key = canonical_entity_key(str(ref["arch_artifact_id"]))
            found.setdefault(element_key, []).append(str(node["node_id"]))
    return found


def _hazards_by_control_node(
    assurance_edges: Sequence[Mapping[str, object]],
    node_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, list[Mapping[str, object]]]:
    """Which hazards each control-structure node is already implicated in.

    Two routes, both already in the model: an unsafe control action attributed to the controller and
    leading to a hazard, and a loss scenario that concerns the node and explains a hazard. Nothing
    new is inferred — these are the links the hazard analysis drew.
    """
    def _targets(source: str, conn_type: str) -> list[str]:
        return [
            str(e["target_id"]) for e in assurance_edges
            if str(e.get("source_id")) == source and str(e.get("conn_type")) == conn_type
        ]

    implicated: dict[str, set[str]] = {}
    for edge in assurance_edges:
        conn = str(edge.get("conn_type"))
        source = str(edge.get("source_id"))
        target = str(edge.get("target_id"))
        source_type = str((node_by_id.get(source) or {}).get("node_type", ""))
        if conn == "by-controller" and source_type == "unsafe-control-action":
            implicated.setdefault(target, set()).update(_targets(source, LEADS_TO))
        elif conn == "concerns" and source_type == "loss-scenario":
            implicated.setdefault(target, set()).update(_targets(source, "explains"))
    return {
        control_node: [
            node_by_id[h] for h in sorted(hazards)
            if str((node_by_id.get(h) or {}).get("node_type", "")) == "hazard"
        ]
        for control_node, hazards in implicated.items()
    }


def suggest_effects(
    element_id: str,
    *,
    nodes: Sequence[Mapping[str, object]],
    arch_refs: Sequence[Mapping[str, object]],
    edges: Sequence[TypedEdge],
    assurance_edges: Sequence[Mapping[str, object]] = (),
    max_hops: int = DEFAULT_MAX_HOPS,
) -> tuple[EffectSuggestion, ...]:
    """Hazards reachable from `element_id` through elements a control structure already names.

    Ordered strongest path first, then fewest hops, then by id so the list is stable between runs —
    a suggestion list that reshuffles is one an analyst stops reading.
    """
    node_by_id = {str(n["node_id"]): n for n in nodes}
    by_element = _control_nodes_by_element(arch_refs, node_by_id)
    by_control_node = _hazards_by_control_node(assurance_edges, node_by_id)
    reachable = _reachable(canonical_entity_key(element_id), edges, max_hops=max_hops)

    found: list[EffectSuggestion] = []
    seen: set[str] = set()
    for neighbour_id, (hops, strength, path) in reachable.items():
        for control_node_id in by_element.get(neighbour_id, ()):
            for hazard in by_control_node.get(control_node_id, ()):
                hazard_id = str(hazard["node_id"])
                if hazard_id in seen:
                    continue
                seen.add(hazard_id)
                found.append(EffectSuggestion(
                    hazard_id=hazard_id,
                    hazard_name=str(hazard.get("name") or ""),
                    via_element_id=neighbour_id,
                    strength=strength,
                    hops=hops,
                    witness=(*path, f"{neighbour_id} is analysed as {control_node_id}"),
                ))
    return tuple(sorted(found, key=lambda s: (-s.strength, s.hops, s.hazard_id)))
