"""A composed child is drawn *inside* its parent, not beside it.

ArchiMate composition is strict containment, and the notation says so by nesting: a process
decomposed into functions, sub-processes and events draws those inside its own box; a function
decomposed into sub-functions likewise. Drawn as a peer box joined by a line, the picture
asserts a relationship the model does not contain and loses the one it does.

The machinery for this was already in place and correct — `archimate-composition` carries
`classes: [containment, nesting]`, and each ArchiMate diagram type declares which of those
classes nest — but nothing exercised it end to end. So when a diagram's stored body turned out
never to be re-derived from the model, the missing nesting looked like a renderer defect and
had to be bisected out of the write path. These tests hold the renderer's half of that
boundary, so the next time nesting goes missing from a picture the cause is not in question.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from src.application.puml_alias_declarations import declared_aliases
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body


def _entity(artifact_id: str, artifact_type: str, name: str, alias: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain="business",
        subdomain="processes",
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=alias,
    )


def _conn(source: str, target: str, conn_type: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source}---{target}@@{conn_type}",
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("/tmp/test.outgoing.md"),
        extra={},
        content_text="",
        src_multiplicity="",
        tgt_multiplicity="",
    )


PARENT = "PRC@1.parent"
CHILD_A = "FNC@1.childa"
CHILD_B = "FNC@1.childb"
OUTSIDER = "APP@1.outsider"


def _records() -> tuple[list[EntityRecord], list[ConnectionRecord]]:
    entities = [
        _entity(PARENT, "process", "Synchronize With Remote", "PRC_parent"),
        _entity(CHILD_A, "function", "Check Workspace Status", "FNC_childa"),
        _entity(CHILD_B, "function", "Pull Repository Changes", "FNC_childb"),
        _entity(OUTSIDER, "application-component", "Git Sync Service", "APP_outsider"),
    ]
    connections = [
        _conn(PARENT, CHILD_A, "archimate-composition"),
        _conn(PARENT, CHILD_B, "archimate-composition"),
        _conn(OUTSIDER, PARENT, "archimate-association"),
    ]
    return entities, connections


def _declaration_line(body: str, alias: str) -> str:
    """The line declaring `alias`, which is where any nesting brace opens."""
    for line in body.splitlines():
        if re.search(rf"\bas {re.escape(alias)}\b", line):
            return line
    raise AssertionError(f"{alias} is not declared in the body at all:\n{body}")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


class TestCompositionNests:
    """The positive contract, on the shape that motivated it: a process over two functions."""

    def test_a_composed_child_is_declared_inside_its_parents_block(self) -> None:
        entities, connections = _records()

        body = generate_archimate_puml_body(
            "Containment", entities, connections, diagram_type="archimate-application"
        )

        parent_line = _declaration_line(body, "PRC_parent")
        assert parent_line.rstrip().endswith("{"), (
            "the parent declares no nested block, so its children cannot be inside it:\n"
            f"{parent_line}"
        )
        for child in ("FNC_childa", "FNC_childb"):
            assert _indent(_declaration_line(body, child)) > _indent(parent_line), (
                f"{child} is drawn beside its parent rather than within it:\n{body}"
            )

    def test_a_nested_child_gets_no_drawn_edge_to_its_parent(self) -> None:
        """Containment is expressed by the nesting itself. An edge as well would draw the
        same fact twice, and is what a reader sees as 'peer box joined by a line'."""
        entities, connections = _records()

        body = generate_archimate_puml_body(
            "Containment", entities, connections, diagram_type="archimate-application"
        )

        for child in ("FNC_childa", "FNC_childb"):
            drawn = [
                line for line in body.splitlines()
                if "PRC_parent" in line and child in line and "-[hidden]" not in line
                and " as " not in line
            ]
            assert drawn == [], f"composition to {child} is drawn as an edge as well:\n{drawn}"

    def test_a_non_containment_neighbour_stays_outside_the_parent(self) -> None:
        """Only containment nests. An association must not drag its partner inside."""
        entities, connections = _records()

        body = generate_archimate_puml_body(
            "Containment", entities, connections, diagram_type="archimate-application"
        )

        parent_line = _declaration_line(body, "PRC_parent")
        assert _indent(_declaration_line(body, "APP_outsider")) <= _indent(parent_line)


class TestNestingHoldsAcrossArchimateDiagramTypes:
    """Nesting is declared per diagram type, so it is asserted per diagram type — a type that
    forgets to declare its nesting classes renders containment flat and nothing else notices."""

    @pytest.mark.parametrize(
        "diagram_type", ["archimate-application", "archimate-business", "archimate-layered"]
    )
    def test_composition_nests(self, diagram_type: str) -> None:
        entities, connections = _records()

        body = generate_archimate_puml_body(
            "Containment", entities, connections, diagram_type=diagram_type
        )

        parent_line = _declaration_line(body, "PRC_parent")
        assert parent_line.rstrip().endswith("{"), f"{diagram_type} draws containment flat"
        assert _indent(_declaration_line(body, "FNC_childa")) > _indent(parent_line), (
            f"{diagram_type} draws a composed child beside its parent"
        )


def _declaration_counts(body: str) -> Counter[str]:
    """How often the body declares each alias, read through the module that owns the syntax."""
    return Counter(declaration.alias for declaration in declared_aliases(body))


def _drawn_between(body: str, left: str, right: str) -> list[str]:
    """The arrow lines joining the pair — layout chains and declarations are not arrows."""
    return [
        line.strip()
        for line in body.splitlines()
        if left in line and right in line and "-[hidden]" not in line and " as " not in line
    ]


class TestVisualNestingIsAForest:
    """PlantUML containment is a tree; the model's containment graph is not.

    An element aggregated by two parents was emitted inside *each* of them, with the same alias
    both times. PlantUML reads the second `as ALIAS` as a *reference* to the element it already
    created, so the second container renders EMPTY and that containment leaves the picture — and
    nothing objected, because the body parses and every id in it still resolves. Measured on the
    view that reported it: 29 declarations for 19 aliases, four empty region boxes.

    The containment that cannot be nested is not dropped: it is drawn as its own arrow, which the
    connection renderer already did for any containment the picture does not nest.
    """

    def _two_parents(self) -> tuple[list[EntityRecord], list[ConnectionRecord]]:
        """The reported shape: a region and a subscription aggregating one environment."""
        entities = [
            _entity("GRP@1.sub", "grouping", "Azure Subscription", "GRP_sub"),
            _entity("LOC@1.region", "location", "West Europe", "LOC_region"),
            _entity("GRP@1.env", "grouping", "Development Environment", "GRP_env"),
        ]
        connections = [
            _conn("GRP@1.sub", "GRP@1.env", "archimate-aggregation"),
            _conn("LOC@1.region", "GRP@1.env", "archimate-aggregation"),
        ]
        return entities, connections

    def test_an_element_with_two_parents_is_declared_once(self) -> None:
        entities, connections = self._two_parents()

        body = generate_archimate_puml_body(
            "Two parents", entities, connections, diagram_type="archimate-technology"
        )

        duplicated = {alias: n for alias, n in _declaration_counts(body).items() if n > 1}
        assert duplicated == {}, (
            "an alias declared twice makes the second container render empty:\n"
            f"{duplicated}\n{body}"
        )

    def test_the_containment_that_could_not_nest_is_drawn_as_an_arrow(self) -> None:
        """Losing the box must not mean losing the relation — the picture still asserts it."""
        entities, connections = self._two_parents()

        body = generate_archimate_puml_body(
            "Two parents", entities, connections, diagram_type="archimate-technology"
        )

        nested_under_first = _indent(_declaration_line(body, "GRP_env")) > _indent(
            _declaration_line(body, "GRP_sub")
        )
        assert nested_under_first, "the first declared parent keeps the nesting"
        assert _drawn_between(body, "LOC_region", "GRP_env"), (
            f"the second parent's aggregation is in neither the nesting nor an arrow:\n{body}"
        )

    def test_a_twice_parented_elements_own_children_are_not_duplicated_either(self) -> None:
        """The duplication was recursive: the whole subtree was emitted under each parent."""
        entities, connections = self._two_parents()
        entities.append(_entity("NOD@1.host", "node", "Build Host", "NOD_host"))
        connections.append(_conn("GRP@1.env", "NOD@1.host", "archimate-aggregation"))

        body = generate_archimate_puml_body(
            "Subtree", entities, connections, diagram_type="archimate-technology"
        )

        assert _declaration_counts(body)["NOD_host"] == 1, body

    def test_three_parents_leave_one_nesting_and_two_arrows(self) -> None:
        entities, connections = self._two_parents()
        entities.append(_entity("GRP@1.tenant", "grouping", "Tenant", "GRP_tenant"))
        connections.append(_conn("GRP@1.tenant", "GRP@1.env", "archimate-aggregation"))

        body = generate_archimate_puml_body(
            "Three parents", entities, connections, diagram_type="archimate-technology"
        )

        assert _declaration_counts(body)["GRP_env"] == 1, body
        assert _drawn_between(body, "LOC_region", "GRP_env"), body
        assert _drawn_between(body, "GRP_tenant", "GRP_env"), body

    def test_a_containment_cycle_still_draws_both_elements(self) -> None:
        """Every element nested and none left to declare emitted an EMPTY diagram: with A inside B
        and B inside A, neither was a root, so the body declared nothing at all."""
        entities = [
            _entity("GRP@1.a", "grouping", "A", "GRP_a"),
            _entity("GRP@1.b", "grouping", "B", "GRP_b"),
        ]
        connections = [
            _conn("GRP@1.a", "GRP@1.b", "archimate-aggregation"),
            _conn("GRP@1.b", "GRP@1.a", "archimate-aggregation"),
        ]

        body = generate_archimate_puml_body(
            "Cycle", entities, connections, diagram_type="archimate-technology"
        )

        counts = _declaration_counts(body)
        assert counts["GRP_a"] == 1 and counts["GRP_b"] == 1, (
            f"a containment cycle must still draw its elements:\n{body}"
        )

    def test_an_element_containing_itself_is_drawn_once(self) -> None:
        entities = [_entity("GRP@1.a", "grouping", "A", "GRP_a")]
        connections = [_conn("GRP@1.a", "GRP@1.a", "archimate-aggregation")]

        body = generate_archimate_puml_body(
            "Self", entities, connections, diagram_type="archimate-technology"
        )

        assert _declaration_counts(body)["GRP_a"] == 1, body


class TestFunctionDecomposition:
    """The other half of the user-stated requirement: a function into sub-functions."""

    def test_a_function_nests_its_sub_functions(self) -> None:
        entities = [
            _entity("FNC@1.outer", "function", "Index Repository", "FNC_outer"),
            _entity("FNC@1.inner", "function", "Build Connection Graph", "FNC_inner"),
        ]
        connections = [_conn("FNC@1.outer", "FNC@1.inner", "archimate-composition")]

        body = generate_archimate_puml_body(
            "Decomposition", entities, connections, diagram_type="archimate-application"
        )

        outer_line = _declaration_line(body, "FNC_outer")
        assert outer_line.rstrip().endswith("{")
        assert _indent(_declaration_line(body, "FNC_inner")) > _indent(outer_line)
