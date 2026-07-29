"""The bowtie renderer — one implementation, two content sources.

A bowtie centres on a hazard (the *top event*): threat pathways enter from the left, consequences
leave to the right, and barriers interrupt each pathway between. It is drawn from either the live
confidential store or the `diagram-entities` snapshot of a persisted bowtie diagram, and both hand
over the same node and edge dicts — so there is no reason for two renderers.

There were two, and they had drifted in a way that cost content: the live projection derived a node's
role from its `node_type` and knew only four roles, so **`barrier_right` could not be drawn at all**
— in a diagram whose entire point is barriers on both sides of the top event. It also dropped nodes
whose role it did not recognise, where the other kept them.

The reconciled rule for a node's role: an explicitly authored `role` wins, because a persisted
diagram may say things the store's type vocabulary cannot; otherwise the role is derived from
`node_type` — and for a constraint, from whether it mitigates a loss, which is the one thing the
node alone cannot tell you. Nothing is dropped for having an unfamiliar *role* — an unplaced node in
a bowtie is a modelling gap worth seeing.

Having no *pathway* is a different matter, and only the live projection judges it: see
`project_store_graph`. A persisted bowtie keeps whatever its author drew, because they drew it on
purpose; a projection has to decide what the bowtie is about, and a node nothing in the diagram links
to is not part of it.
"""

from __future__ import annotations

import re
from collections.abc import Container, Mapping, Sequence

from src.diagram_types._assurance_puml_alias import safe_alias

THREAT = "threat"
BARRIER_LEFT = "barrier_left"
TOP_EVENT = "top_event"
BARRIER_RIGHT = "barrier_right"
CONSEQUENCE = "consequence"

#: Left-to-right reading order of a bowtie: what can happen, what stops it, the event itself, what
#: limits the damage, and what the damage is.
ROLE_ORDER: tuple[str, ...] = (THREAT, BARRIER_LEFT, TOP_EVENT, BARRIER_RIGHT, CONSEQUENCE)

#: The relation that puts a barrier on the consequence side: a constraint which does not prevent the
#: top event but limits a loss once it has occurred. The threat side needs no counterpart relation —
#: it is what a constraint's `derives` provenance already says — so the absence of `mitigates` is
#: itself the statement that a barrier is preventive.
MITIGATES = "mitigates"

#: Store node type → bowtie role, for content that carries no explicit role.
#:
#: An `assurance-constraint` lands on the left unless it `mitigates` a loss; see `role_of`.
ROLE_BY_NODE_TYPE: Mapping[str, str] = {
    "unsafe-control-action": THREAT,
    "loss-scenario": THREAT,
    "assurance-constraint": BARRIER_LEFT,
    "hazard": TOP_EVENT,
    "loss": CONSEQUENCE,
}

#: role → (PlantUML keyword, background colour, stereotype). Barriers are cards so they read as
#: interventions rather than as stages of the chain.
ROLE_STYLE: Mapping[str, tuple[str, str, str]] = {
    THREAT: ("component", "#FFD0D0", "<<threat>>"),
    BARRIER_LEFT: ("card", "#D0FFD0", "<<barrier>>"),
    TOP_EVENT: ("component", "#FFB060", "<<top-event>>"),
    BARRIER_RIGHT: ("card", "#D0FFD0", "<<barrier>>"),
    CONSEQUENCE: ("component", "#FFD0D0", "<<consequence>>"),
}
_UNPLACED_STYLE: tuple[str, str, str] = ("component", "#White", "")

_EMPTY_NOTE = 'note "No bowtie assurance nodes found." as N1'
_NON_ALIAS_CHARS = re.compile(r"[^A-Za-z0-9_]")
_REPEATED_UNDERSCORE = re.compile(r"_+")


def _quote(text: str) -> str:
    return '"' + text.replace('"', "'") + '"'


def mitigating_barrier_ids(edges: Sequence[Mapping[str, object]]) -> frozenset[str]:
    """Ids of the constraints that mitigate a loss — the barriers belonging right of the top event."""
    return frozenset(
        str(edge.get("source_id", "")) for edge in edges
        if str(edge.get("conn_type", "")) == MITIGATES
    )


def role_of(node: Mapping[str, object], *, mitigating_ids: Container[str] = frozenset()) -> str:
    """A node's bowtie role: authored if stated, else derived from its store node type and edges.

    An authored role wins so a persisted diagram can place a node however it was drawn. Otherwise a
    constraint sits left of the top event — the side its `derives` provenance already implies —
    unless it appears in `mitigating_ids`, which puts it right. An empty role means "unplaced", not
    "excluded".
    """
    authored = str(node.get("role") or "")
    if authored:
        return authored
    derived = ROLE_BY_NODE_TYPE.get(str(node.get("node_type", "")), "")
    if derived == BARRIER_LEFT and str(node.get("node_id", "")) in mitigating_ids:
        return BARRIER_RIGHT
    return derived


def participates(node: Mapping[str, object]) -> bool:
    """Whether this node belongs in a bowtie at all — i.e. whether it has a role here.

    Which side a barrier takes never decides whether it takes part, so this needs no edge context.
    """
    return bool(role_of(node))


def project_store_graph(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """The sub-graph a bowtie draws: nodes with a bowtie role, and the edges between them.

    A mitigative barrier is stamped with its `role`, so the side survives into a persisted snapshot
    and does not have to be re-derived by whatever handles the projection next. Callers filter for
    exposure *before* projecting, so a barrier whose loss is above the caller's clearance loses the
    edge that placed it and falls back to the preventive side — the placement degrades rather than
    disclosing that a loss it protects against exists.

    **A node on no drawn pathway is not part of the bowtie.** A bowtie is a picture of pathways, and a
    constraint whose only relations run to node types this notation does not draw — a failure mode
    that derives it, an obligation it complies with, the evidence that exercises it — has no pathway
    here. Kept, it renders as a box with no lines touching it, which reads as a broken diagram rather
    than as the coverage gap it might be. That gap is the verifier's to report, where it can say
    *which* link is missing; this notation's job is to draw the pathways that exist.
    """
    mitigating = mitigating_barrier_ids(edges)
    participating: list[dict[str, object]] = []
    for node in nodes:
        if not participates(node):
            continue
        drawn = dict(node)
        drawn["role"] = role_of(node, mitigating_ids=mitigating)
        participating.append(drawn)
    ids = {str(n["node_id"]) for n in participating}
    between = [
        dict(e) for e in edges
        if str(e.get("source_id", "")) in ids and str(e.get("target_id", "")) in ids
    ]
    linked = {str(e["source_id"]) for e in between} | {str(e["target_id"]) for e in between}
    return [node for node in participating if str(node["node_id"]) in linked], between


def _ordered(
    nodes: Sequence[Mapping[str, object]],
    mitigating_ids: Container[str],
) -> list[Mapping[str, object]]:
    """Left to right along the bowtie, then by name so a redraw is stable.

    Unplaced nodes come last rather than being dropped: a node in a bowtie projection with no role is
    a modelling gap, and a diagram that silently omits it hides the gap.
    """
    def sort_key(node: Mapping[str, object]) -> tuple[int, str]:
        role = role_of(node, mitigating_ids=mitigating_ids)
        position = ROLE_ORDER.index(role) if role in ROLE_ORDER else len(ROLE_ORDER)
        return position, str(node.get("name", node.get("node_id", "")))

    return sorted(nodes, key=sort_key)


def arrow_label(edge: Mapping[str, object]) -> str:
    """An edge's label: authored name or label, else its connection type."""
    for key in ("label", "name", "conn_type"):
        value = edge.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def render(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
    *,
    title: str = "",
) -> str:
    """Render a bowtie as PlantUML, left to right through the top event."""
    opening = f"@startuml {safe_alias(title)}" if title else "@startuml"
    lines: list[str] = [opening, "left to right direction", ""]

    mitigating = mitigating_barrier_ids(edges)
    ordered = _ordered(nodes, mitigating)
    for node in ordered:
        role = role_of(node, mitigating_ids=mitigating)
        keyword, colour, stereotype = ROLE_STYLE.get(role, _UNPLACED_STYLE)
        node_id = str(node.get("node_id", ""))
        label = _quote(str(node.get("name", node_id)))
        suffix = f" {stereotype}" if stereotype else ""
        lines.append(f"{keyword} {label}{suffix} as {safe_alias(node_id)} {colour}")

    if ordered:
        lines.append("")

    for edge in edges:
        source = safe_alias(str(edge.get("source_id", "")))
        target = safe_alias(str(edge.get("target_id", "")))
        label = arrow_label(edge)
        suffix = f" : {_quote(label)}" if label else ""
        lines.append(f"{source} --> {target}{suffix}")

    if not ordered:
        lines.append(_EMPTY_NOTE)

    lines.extend(["", "@enduml"])
    return "\n".join(lines)
