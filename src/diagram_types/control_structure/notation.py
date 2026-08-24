"""The STAMP control-structure renderer — one implementation, two content sources.

A control structure is drawn from either of two places, and the content is assurance content in
both cases: the **live** confidential store, or the `diagram-entities` frontmatter of a persisted
control-structure diagram (a snapshot, redirected to a gitignored location unless it is classified
TLP:WHITE/GREEN). Both hand over the same thing — a list of node dicts and a list of edge dicts —
so there is no reason for two renderers, and the two that existed had drifted: the same bare-glyph
defect in both, feedback reversed in one, and the "unbound node is a visible modelling gap" signal
the documentation promises implemented only in the one nobody looks at.

`render()` is that single implementation, and it lives with the diagram type whose notation it is —
rendering a control structure is the control-structure diagram type's job. Its callers are thin
adapters: the diagram-type renderer normalises frontmatter first, and the live projection passes the
store's nodes and edges straight through.

Notation, per the convention the STPA literature established (Leveson, *Engineering a Safer
World*; Leveson & Thomas, *STPA Handbook*):

  * Controllers and controlled processes are **boxes**.
  * A control action is the **arrow** from a controller to what it controls, labelled with the
    command. The store models it as a node — unsafe control actions are enumerated per action,
    and an action carries its own status, TLP, and architecture binding — so only the *drawing*
    collapses, and the arrow keeps the action's identity (`collapsed_control_action_links`).
  * Feedback is the arrow back up the loop. Every edge is drawn in the direction it was
    authored; feedback is authored the way it flows, so reversing it inverts the loop.

Styling that carries meaning is here too (binding status). Styling that is merely each surface's
own look — the skinparam blocks, layout hints — stays with the renderer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.diagram_types._assurance_puml_alias import safe_alias
from src.domain.assurance.assurance_node_types import CONTROL_STRUCTURE_NODE
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams

_NON_ALIAS_CHARS = re.compile(r"[^A-Za-z0-9_]")
_REPEATED_UNDERSCORE = re.compile(r"_+")

# ── The control loop's vocabulary ─────────────────────────────────────────────
# Named after the assurance ontology's permitted relationships:
# `control-structure-node --issues--> control-action --acts-on--> control-structure-node`,
# with `feedback` between two control-structure nodes. Matched by name rather than inferred
# from direction: other relationships also point at a control action (a UCA `concerns` one)
# and none of those is part of the loop.
ISSUES = "issues"
ACTS_ON = "acts-on"
ACTS_THROUGH = "acts-through"
FEEDBACK = "feedback"
LOOP_CONNECTION_TYPES = frozenset({ISSUES, ACTS_ON, ACTS_THROUGH})

CONTROL_ACTION = "control-action"

#: Stereotype a control action carries. It is also what its styling keys off, so it is never
#: dropped in favour of a (usually absent) node role.
CONTROL_ACTION_STEREOTYPE = "control action"

#: Binding status → (PlantUML element colour, name marker). A node not yet tied to an
#: architecture entity is a modelling gap the diagram is supposed to show, so the signal belongs
#: to the notation rather than to one renderer. `bound` contributes no explicit colour, leaving
#: each surface's own fill in place — an explicit element colour would override it.
_BINDING_STYLES: Mapping[str, tuple[str, str]] = {
    "bound": ("", ""),
    "unbound-pending": ("#LightYellow", " [?]"),
    "out-of-scope": ("#LightGray", " [~]"),
}
_DEFAULT_BINDING_STYLE = ("", "")


def binding_style(binding_status: str | None) -> tuple[str, str]:
    """The colour override and name marker for a node's binding status."""
    return _BINDING_STYLES.get(str(binding_status or "bound"), _DEFAULT_BINDING_STYLE)


def stereotype_for(node: Mapping[str, object]) -> str:
    """The stereotype text for a node — its role, or `control action` for a control action.

    Returned without `<<>>` so a caller can place it in its own syntax. Hyphens become spaces:
    the stereotype is read by a person, not matched by a machine.
    """
    if str(node.get("node_type", "")) == CONTROL_ACTION:
        return CONTROL_ACTION_STEREOTYPE
    return str(node.get("node_role") or "").replace("-", " ")


def arrow_label(edge: Mapping[str, object]) -> str:
    """What an edge's arrow is labelled with.

    An authored name wins over the bare connection type: "feedback" says only which half of the
    loop this is, not *what it carries*, and a control structure whose arrows all read "feedback"
    tells an analyst nothing. The store has no name column for an edge, so an author puts it in the
    edge's `attributes` — read here whether that arrives parsed (frontmatter) or as the store's JSON
    string.
    """
    for key in ("name", "label"):
        direct = edge.get(key)
        if isinstance(direct, str) and direct:
            return direct
    for key in ("name", "label"):
        authored = _edge_attributes(edge).get(key)
        if isinstance(authored, str) and authored:
            return authored
    return str(edge.get("conn_type") or "")


def _edge_attributes(edge: Mapping[str, object]) -> Mapping[str, object]:
    """An edge's `attributes`, from either a parsed mapping or the store's `attributes_json`."""
    for key in ("attributes", "attributes_json"):
        raw = edge.get(key)
        if isinstance(raw, Mapping):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}


# ── Partitioning the projection ───────────────────────────────────────────────


def control_structure_nodes(nodes: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Controllers, controlled processes, actuators, sensors — everything drawn as a box."""
    return [n for n in nodes if str(n.get("node_type", "")) == CONTROL_STRUCTURE_NODE]


def control_actions(nodes: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return [n for n in nodes if str(n.get("node_type", "")) == CONTROL_ACTION]


def node_ids(nodes: Iterable[Mapping[str, object]]) -> set[str]:
    return {str(n["node_id"]) for n in nodes}


def _incident_edges(
    node_id: str,
    edges: Iterable[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return [
        e for e in edges
        if node_id in {str(e.get("source_id", "")), str(e.get("target_id", ""))}
    ]


# ── Collapsing a control action into its arrow ────────────────────────────────


@dataclass(frozen=True)
class ControlPath:
    """Where one control action sits in its loop: who issues it, what effects it, what it controls.

    `actuators` is the canonical loop's third position — the element a command is effected through
    (`acts-through`). When present the command is drawn along the path it actually takes, controller
    → actuator → process, which is how the STPA literature draws it; when absent the two ends are
    joined directly.
    """

    controllers: tuple[str, ...]
    actuators: tuple[str, ...]
    processes: tuple[str, ...]

    def hops(self) -> list[tuple[str, str, bool]]:
        """The arrows that draw this action: (source, target, carries_the_command_label).

        The command labels the hop that *issues* it — controller → actuator when a mediator is
        named, controller → process otherwise. The actuator's own hop to the process carries no
        label: it is the same command being effected, not a second one.
        """
        if not self.actuators:
            return [(c, p, True) for c in self.controllers for p in self.processes]
        return [
            *[(c, a, True) for c in self.controllers for a in self.actuators],
            *[(a, p, False) for a in self.actuators for p in self.processes],
        ]


def drawn_as_arrow(
    action_id: str,
    edges: Sequence[Mapping[str, object]],
    box_ids: set[str],
) -> ControlPath | None:
    """The path this action is drawn along, or None to keep it a box.

    Two things disqualify the arrow, both because it would lose what a box keeps: an
    **incomplete loop** (no controller, or nothing acted on) is a modelling gap that has to stay
    visible, and an action that anything **else** connects to needs a shape for that edge to land
    on.
    """
    controllers: list[str] = []
    actuators: list[str] = []
    processes: list[str] = []
    for edge in _incident_edges(action_id, edges):
        conn_type = str(edge.get("conn_type", ""))
        source = str(edge.get("source_id", ""))
        target = str(edge.get("target_id", ""))
        if conn_type == ISSUES and target == action_id and source in box_ids:
            controllers.append(source)
        elif conn_type == ACTS_ON and source == action_id and target in box_ids:
            processes.append(target)
        elif conn_type == ACTS_THROUGH and source == action_id and target in box_ids:
            actuators.append(target)
        else:
            return None  # something outside the loop is attached to this action
    if not controllers or not processes:
        return None
    return ControlPath(tuple(controllers), tuple(actuators), tuple(processes))


def collapsed_control_action_links(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Which arrows in the rendered structure *are* a control action.

    A control action drawn as an arrow still has to be reachable: its unsafe control actions,
    status, TLP, and architecture binding all hang off the node. A viewer uses this to route a
    click on the arrow to the action it draws.
    """
    box_ids = node_ids(control_structure_nodes(nodes))
    links: list[dict[str, str]] = []
    for action in control_actions(nodes):
        action_id = str(action["node_id"])
        path = drawn_as_arrow(action_id, edges, box_ids)
        if path is None:
            continue
        # Every hop of the path draws the same action, so every hop selects it — including an
        # actuator's unlabelled hop, which is the reader's most natural place to click.
        links.extend(
            {"control_action_id": action_id, "controller_id": source, "process_id": target}
            for source, target, _labelled in path.hops()
        )
    return links


def partition_for_drawing(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], dict[str, ControlPath], set[str]]:
    """Split a projection into what is drawn how.

    Returns the nodes that keep a box (control-structure nodes plus any control action that cannot
    be collapsed), the path each collapsed action is drawn along, and the ids of those actions —
    whose own edges must not then be drawn again.
    """
    boxes = control_structure_nodes(nodes)
    box_ids = node_ids(boxes)
    paths: dict[str, ControlPath] = {}
    for action in control_actions(nodes):
        action_id = str(action["node_id"])
        path = drawn_as_arrow(action_id, edges, box_ids)
        if path is not None:
            paths[action_id] = path
    boxed_actions = [a for a in control_actions(nodes) if str(a["node_id"]) not in paths]
    return [*boxes, *boxed_actions], paths, set(paths)


# ── The renderer ──────────────────────────────────────────────────────────────

_SKINPARAMS: tuple[str, ...] = (
    # A controller's box is as wide as its unwrapped name, and an STPA controller's name is a
    # phrase, not a word — the picture grew sideways until nothing but the boxes fit.
    *label_wrap_skinparams({}),
    "skinparam rectangle {",
    "  BackgroundColor #EBF5FB",
    "  BorderColor #2E86C1",
    "}",
    f"skinparam rectangle<<{CONTROL_ACTION_STEREOTYPE}>> {{",
    "  BackgroundColor #FDF2E0",
    "  BorderColor #B9770E",
    "}",
)

_EMPTY_NOTE = 'note "No control-structure nodes found." as N1'


def _quote(text: str) -> str:
    return '"' + text.replace('"', "'") + '"'


def render(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
    *,
    title: str = "",
) -> str:
    """Render a control structure as PlantUML.

    Boxes for controllers and controlled processes; a control action as the labelled arrow between
    its endpoints where the loop allows it, and as a box where collapsing would hide something.
    Every edge keeps the direction it was authored in, with feedback dotted so the two halves of a
    loop read differently.
    """
    boxed, paths, collapsed = partition_for_drawing(nodes, edges)
    shown_ids = node_ids(boxed)
    actions_by_id = {str(a["node_id"]): a for a in control_actions(nodes)}

    opening = f"@startuml {safe_alias(title)}" if title else "@startuml"
    lines: list[str] = [opening, *_SKINPARAMS]

    for node in boxed:
        colour, marker = binding_style(str(node.get("binding_status") or ""))
        name = _quote(f"{node.get('name', node['node_id'])}{marker}")
        # A stereotype renders on its own line below the label and must sit OUTSIDE the quoted
        # label with a plain space separator; a literal newline escape there is invalid PlantUML
        # and fails the whole render.
        stereotype = stereotype_for(node)
        suffix = f" <<{stereotype}>>" if stereotype else ""
        colour_suffix = f" {colour}" if colour else ""
        lines.append(f"rectangle {name}{suffix} as {safe_alias(str(node['node_id']))}{colour_suffix}")

    for action_id, path in paths.items():
        label = _quote(str(actions_by_id[action_id].get("name", action_id)))
        for source, target, labelled in path.hops():
            suffix = f" : {label}" if labelled else ""
            lines.append(f"{safe_alias(source)} --> {safe_alias(target)}{suffix}")

    for edge in edges:
        source = str(edge.get("source_id", ""))
        target = str(edge.get("target_id", ""))
        # An edge into or out of a collapsed action is already drawn *as* that action's arrow;
        # drawing it again would restate "issues"/"acts-on" beside the command name.
        if collapsed & {source, target}:
            continue
        if source not in shown_ids or target not in shown_ids:
            continue
        label = arrow_label(edge)
        label_part = f" : {_quote(label)}" if label else ""
        arrow = "..>" if str(edge.get("conn_type", "")) == FEEDBACK else "-->"
        lines.append(f"{safe_alias(source)} {arrow} {safe_alias(target)}{label_part}")

    if not boxed:
        lines.append(_EMPTY_NOTE)

    lines.append("@enduml")
    return "\n".join(lines)


def project_store_graph(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """The sub-graph a control structure draws: structural nodes and control actions, plus the edges
    between them. A hazard or a UCA is assurance content but not part of the control structure."""
    participating = [
        dict(n) for n in nodes
        if str(n.get("node_type", "")) in {CONTROL_STRUCTURE_NODE, CONTROL_ACTION}
    ]
    ids = {str(n["node_id"]) for n in participating}
    between = [
        dict(e) for e in edges
        if str(e.get("source_id", "")) in ids and str(e.get("target_id", "")) in ids
    ]
    return participating, between


def node_representing_edges(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    """The drawn edges that stand for a node, in the generic shape a viewer consumes.

    Here that is every control action collapsed into its arrow: the node it represents plus the
    endpoints of the arrow that draws it.
    """
    return [
        {
            "node_id": link["control_action_id"],
            "source_id": link["controller_id"],
            "target_id": link["process_id"],
        }
        for link in collapsed_control_action_links(nodes, edges)
    ]
