"""The STAMP control-structure renderer — one implementation for both content sources.

The live store projection and the persisted-diagram renderer are thin adapters over `render()`, so
these are the tests for what a control structure *looks like*, wherever its nodes and edges came
from. The regressions they pin: a control action drawn as a bare glyph or a degenerate sliver
instead of the notation's arrow, feedback reversed against the direction it was authored in, and a
collapse that hides a modelling gap.
"""

from __future__ import annotations

from src.diagram_types.control_structure.notation import (
    collapsed_control_action_links,
    render,
)


def _cs_node(nid: str, name: str, role: str = "") -> dict[str, object]:
    return {"node_id": nid, "node_type": "control-structure-node", "name": name, "node_role": role}


def _edge(src: str, tgt: str, conn_type: str, name: str = "") -> dict[str, object]:
    return {"edge_id": f"{src}->{tgt}", "source_id": src, "target_id": tgt,
            "conn_type": conn_type, "name": name}


def render_control_structure(nodes, edges) -> str:
    """Local alias keeping these tests readable — `render` is the renderer under test."""
    return render(nodes, edges)


def test_control_structure_empty_renders_note() -> None:
    puml = render_control_structure([], [])
    assert "@startuml" in puml
    assert "@enduml" in puml
    assert "No control-structure nodes found" in puml


def test_control_structure_single_node() -> None:
    puml = render_control_structure([_cs_node("N1", "Controller")], [])
    assert "Controller" in puml
    assert "rectangle" in puml


def test_control_structure_includes_control_actions_and_their_edges() -> None:
    nodes = [
        _cs_node("N1", "Controller"),
        {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
    ]
    edges = [_edge("N1", "CA1", "issues")]
    puml = render_control_structure(nodes, edges)
    assert "Apply brake" in puml
    assert "issues" in puml


def test_control_action_is_drawn_as_the_labelled_arrow_between_its_endpoints() -> None:
    """STPA notation: a control action is the arrow from a controller to what it controls.

    The command name becomes the arrow's label, and the two edges that carried it — `issues` into
    the action and `acts-on` out of it — are not restated alongside it.
    """
    nodes = [
        _cs_node("N1", "Controller", "controller"),
        _cs_node("N2", "Process", "controlled-process"),
        {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
    ]
    edges = [_edge("N1", "CA1", "issues"), _edge("CA1", "N2", "acts-on")]
    puml = render_control_structure(nodes, edges)

    assert 'N_N1 --> N_N2 : "Apply brake"' in puml
    assert "as N_CA1" not in puml
    assert "issues" not in puml
    assert "acts-on" not in puml


def test_feedback_is_drawn_in_the_direction_it_is_authored() -> None:
    """Feedback is authored the way it flows: from the controlled process up to its controller.

    Regression: the projector reversed every feedback edge, on the assumption that it was authored
    controller-first. Against real content — where feedback is stored process → controller — that
    inverted the observability half of every control loop, pointing feedback at the process.
    """
    nodes = [
        _cs_node("N1", "Controller"),
        _cs_node("N2", "Process"),
        {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
    ]
    edges = [
        _edge("N1", "CA1", "issues"),
        _edge("CA1", "N2", "acts-on"),
        _edge("N2", "N1", "feedback", "brake pressure"),
    ]
    puml = render_control_structure(nodes, edges)

    # The control action goes down the loop solid, the feedback comes back up dotted.
    assert 'N_N1 --> N_N2 : "Apply brake"' in puml
    assert 'N_N2 ..> N_N1 : "brake pressure"' in puml
    assert 'N_N1 ..> N_N2 : "brake pressure"' not in puml


def test_a_process_with_feedback_but_no_control_action_shows_the_one_sided_loop() -> None:
    """A controlled process that reports back but is never commanded is an STPA finding, so the
    projection draws exactly what the model says rather than inventing the missing half."""
    nodes = [_cs_node("N1", "Controller"), _cs_node("N2", "Process")]
    puml = render_control_structure(nodes, [_edge("N2", "N1", "feedback", "status")])

    assert 'N_N2 ..> N_N1 : "status"' in puml
    assert "-->" not in puml, "there is no control action to draw, so nothing goes down the loop"


def test_an_incomplete_control_loop_stays_a_visible_box() -> None:
    """A gap in the model is a finding, so an action with nothing to connect keeps its shape."""
    for edges in ([], [_edge("N1", "CA1", "issues")]):
        nodes = [
            _cs_node("N1", "Controller"),
            {"node_id": "CA1", "node_type": "control-action", "name": "Dangling command"},
        ]
        puml = render_control_structure(nodes, edges)
        assert 'rectangle "Dangling command" <<control action>> as N_CA1' in puml


def test_an_action_other_entities_connect_to_stays_a_box() -> None:
    """An arrow has nowhere to attach a third party's edge, so that action keeps a shape."""
    nodes = [
        _cs_node("N1", "Controller"),
        _cs_node("N2", "Process"),
        _cs_node("N3", "Supervisor"),
        {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
    ]
    edges = [
        _edge("N1", "CA1", "issues"),
        _edge("CA1", "N2", "acts-on"),
        _edge("N3", "CA1", "concerns"),
    ]
    puml = render_control_structure(nodes, edges)

    assert 'rectangle "Apply brake" <<control action>> as N_CA1' in puml
    assert 'N_N1 --> N_N2 : "Apply brake"' not in puml


def test_a_boxed_control_action_keeps_its_stereotype_without_a_role() -> None:
    """The stereotype is what the styling keys off, so it survives an unset node_role."""
    nodes = [{"node_id": "CA1", "node_type": "control-action", "name": "Apply brake", "node_role": None}]
    assert "<<control action>>" in render_control_structure(nodes, [])


def test_every_element_is_declared_as_a_box_never_a_glyph_or_a_sliver() -> None:
    """PlantUML's `control` draws a bare circle-and-arrow icon; a `hexagon` degenerates into a
    sliver for a long command name. Whatever stays a shape is a rectangle."""
    nodes = [
        _cs_node("N1", "Controller", "controller"),
        {"node_id": "CA1", "node_type": "control-action", "name": "Open the store / release the key"},
    ]
    puml = render_control_structure(nodes, [])

    declared_with = {line.split(" ", 1)[0] for line in puml.splitlines() if " as N_" in line}
    assert declared_with == {"rectangle"}
    assert "skinparam rectangle<<control action>> {" in puml


class TestCollapsedControlActionLinks:
    """The arrow that draws a control action must remain identifiable, or the action becomes
    unreachable: its UCAs, TLP, status, and architecture binding all hang off the node."""

    def test_reports_the_arrow_that_stands_for_each_action(self) -> None:
        nodes = [
            _cs_node("N1", "Controller"),
            _cs_node("N2", "Process"),
            {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
        ]
        edges = [_edge("N1", "CA1", "issues"), _edge("CA1", "N2", "acts-on")]

        assert collapsed_control_action_links(nodes, edges) == [
            {"control_action_id": "CA1", "controller_id": "N1", "process_id": "N2"},
        ]

    def test_reports_one_arrow_per_endpoint_pair(self) -> None:
        nodes = [
            _cs_node("N1", "Controller"),
            _cs_node("N2", "Process A"),
            _cs_node("N3", "Process B"),
            {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
        ]
        edges = [_edge("N1", "CA1", "issues"), _edge("CA1", "N2", "acts-on"), _edge("CA1", "N3", "acts-on")]

        assert [link["process_id"] for link in collapsed_control_action_links(nodes, edges)] == ["N2", "N3"]

    def test_reports_nothing_for_an_action_that_stayed_a_box(self) -> None:
        nodes = [
            _cs_node("N1", "Controller"),
            {"node_id": "CA1", "node_type": "control-action", "name": "Dangling command"},
        ]
        assert collapsed_control_action_links(nodes, [_edge("N1", "CA1", "issues")]) == []

    def test_agrees_with_what_was_rendered(self) -> None:
        """The mapping and the drawing are derived from the same rule — a mismatch would leave an
        arrow no click can resolve, or claim an arrow that was never drawn."""
        nodes = [
            _cs_node("N1", "Controller"),
            _cs_node("N2", "Process"),
            {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"},
            {"node_id": "CA2", "node_type": "control-action", "name": "Dangling command"},
        ]
        edges = [_edge("N1", "CA1", "issues"), _edge("CA1", "N2", "acts-on"), _edge("N1", "CA2", "issues")]

        puml = render_control_structure(nodes, edges)
        links = collapsed_control_action_links(nodes, edges)

        assert {link["control_action_id"] for link in links} == {"CA1"}
        assert "as N_CA1" not in puml
        assert "as N_CA2" in puml


def test_control_structure_node_role_in_output() -> None:
    puml = render_control_structure([_cs_node("N1", "Braking", "controller")], [])
    # The role must render as a valid PlantUML stereotype OUTSIDE the quoted label.
    assert '"Braking" <<controller>>' in puml


def test_control_structure_role_emits_no_literal_newline_escape() -> None:
    r"""Regression: the role stereotype was joined to the label with a literal '\n'.

    A backslash-n between a quoted label and its stereotype is invalid PlantUML and
    failed the entire render (every control-structure diagram showed "rendering
    unavailable"). The separator must be a real space, never an escaped newline.
    """
    puml = render_control_structure([_cs_node("N1", "Braking", "controller")], [])
    assert "\\n" not in puml


def test_control_structure_control_action_edge() -> None:
    nodes = [_cs_node("N1", "Ctrl"), _cs_node("N2", "Proc")]
    edges = [_edge("N1", "N2", "control-action", "Apply brake")]
    puml = render_control_structure(nodes, edges)
    assert "-->" in puml
    assert "Apply brake" in puml


def test_feedback_keeps_its_authored_direction_and_reads_as_feedback() -> None:
    """Feedback is authored the way it flows, and is drawn dotted so the two halves of a control
    loop are told apart at a glance."""
    nodes = [_cs_node("N1", "Ctrl"), _cs_node("N2", "Proc")]
    edges = [_edge("N2", "N1", "feedback", "Speed signal")]
    puml = render_control_structure(nodes, edges)

    assert 'N_N2 ..> N_N1 : "Speed signal"' in puml


def test_control_structure_edge_between_non_cs_nodes_excluded() -> None:
    cs_node = _cs_node("N1", "Controller")
    non_cs = {"node_id": "N2", "node_type": "hazard", "name": "Hazard"}
    edges = [_edge("N1", "N2", "leads-to")]
    puml = render_control_structure([cs_node, non_cs], edges)
    assert "leads-to" not in puml


def test_control_structure_alias_safe() -> None:
    node = _cs_node("NOD@1234567890.AbCdEf", "My Node")
    puml = render_control_structure([node], [])
    assert "NOD@1234567890.AbCdEf" not in puml
    assert "N_NOD_1234567890_AbCdEf" in puml


# ── render_uca_matrix ─────────────────────────────────────────────────────────


class TestTheActuatorPosition:
    """The canonical loop has four positions, and both intermediaries have to be drawable.

    Leveson's control loop is controller → actuator → controlled process, with feedback returning
    process → sensor → controller. Without a relation for the execution path, an actuator could only
    be modelled as a second `acts-on` target — which draws it as a second commanded process, the
    opposite of what it is.
    """

    CONTROLLER = _cs_node("CTL", "Controller", "controller")
    ACTUATOR = _cs_node("ACT", "Actuator", "actuator")
    PROCESS = _cs_node("PROC", "Process", "controlled-process")
    SENSOR = _cs_node("SNS", "Sensor", "sensor")
    COMMAND = {"node_id": "CA1", "node_type": "control-action", "name": "Apply brake"}

    def _loop(self, *, mediated: bool) -> str:
        edges = [_edge("CTL", "CA1", "issues"), _edge("CA1", "PROC", "acts-on")]
        if mediated:
            edges.append(_edge("CA1", "ACT", "acts-through"))
        nodes = [self.CONTROLLER, self.PROCESS, self.COMMAND] + ([self.ACTUATOR] if mediated else [])
        return render_control_structure(nodes, edges)

    def test_an_unmediated_command_joins_the_two_ends_directly(self) -> None:
        assert 'N_CTL --> N_PROC : "Apply brake"' in self._loop(mediated=False)

    def test_a_mediated_command_is_drawn_along_the_path_it_takes(self) -> None:
        puml = self._loop(mediated=True)

        assert 'N_CTL --> N_ACT : "Apply brake"' in puml
        assert "N_ACT --> N_PROC" in puml
        assert 'N_CTL --> N_PROC : "Apply brake"' not in puml, "the command does not skip its actuator"

    def test_only_the_issuing_hop_carries_the_command(self) -> None:
        """The actuator's hop is the same command being effected, not a second one."""
        puml = self._loop(mediated=True)

        assert 'N_ACT --> N_PROC : "Apply brake"' not in puml
        assert puml.count("Apply brake") == 1

    def test_an_actuator_is_not_drawn_as_a_second_commanded_process(self) -> None:
        """Modelled with `acts-on` instead, it would be — which is why `acts-through` exists."""
        as_second_target = render_control_structure(
            [self.CONTROLLER, self.ACTUATOR, self.PROCESS, self.COMMAND],
            [_edge("CTL", "CA1", "issues"), _edge("CA1", "PROC", "acts-on"), _edge("CA1", "ACT", "acts-on")],
        )
        assert 'N_CTL --> N_ACT : "Apply brake"' in as_second_target
        assert 'N_CTL --> N_PROC : "Apply brake"' in as_second_target

        mediated = self._loop(mediated=True)
        assert "N_ACT --> N_PROC" in mediated

    def test_every_hop_of_the_path_selects_the_action(self) -> None:
        """A reader clicks whichever arrow is nearest; both draw the same action."""
        edges = [
            _edge("CTL", "CA1", "issues"),
            _edge("CA1", "ACT", "acts-through"),
            _edge("CA1", "PROC", "acts-on"),
        ]
        links = collapsed_control_action_links(
            [self.CONTROLLER, self.ACTUATOR, self.PROCESS, self.COMMAND], edges,
        )

        assert links == [
            {"control_action_id": "CA1", "controller_id": "CTL", "process_id": "ACT"},
            {"control_action_id": "CA1", "controller_id": "ACT", "process_id": "PROC"},
        ]

    def test_the_sensing_path_needs_no_new_relation(self) -> None:
        """`feedback` is already legal between two control-structure nodes, so it chains."""
        puml = render_control_structure(
            [self.CONTROLLER, self.PROCESS, self.SENSOR],
            [
                _edge("PROC", "SNS", "feedback", "raw reading"),
                _edge("SNS", "CTL", "feedback", "verified state"),
            ],
        )

        assert 'N_PROC ..> N_SNS : "raw reading"' in puml
        assert 'N_SNS ..> N_CTL : "verified state"' in puml

    def test_an_actuator_with_no_process_keeps_the_action_as_a_box(self) -> None:
        """Naming an execution path does not complete a loop that has nothing to act on."""
        puml = render_control_structure(
            [self.CONTROLLER, self.ACTUATOR, self.COMMAND],
            [_edge("CTL", "CA1", "issues"), _edge("CA1", "ACT", "acts-through")],
        )
        assert 'rectangle "Apply brake" <<control action>> as N_CA1' in puml
