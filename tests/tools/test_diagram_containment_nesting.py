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
from pathlib import Path

import pytest

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
