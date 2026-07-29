"""Tests for materialization helper functions and DiagramElementRef.

Tests cover the pure (no-I/O) helpers and the dry-run path of the
materialization functions. The full commit path is tested via integration
tests in the broader test suite once a full repo fixture is available.
"""

from __future__ import annotations

from src.domain.diagrams.bindings import Binding, BindingSubject, Target
from src.infrastructure.write.artifact_write.materialization import (
    DiagramElementRef,
    diagram_connection_endpoints,
    diagram_entity_exists,
    filter_bindings,
    find_represents_entity,
)

# ---------------------------------------------------------------------------
# DiagramElementRef
# ---------------------------------------------------------------------------


def test_diagram_element_ref_defaults() -> None:
    ref = DiagramElementRef(diagram_id="DGR@123", diagram_element_id="elem-1")
    assert ref.diagram_element_kind == "entity"
    assert ref.correspondence_kind_after == "represents"


def test_diagram_element_ref_custom() -> None:
    ref = DiagramElementRef(
        diagram_id="DGR@123",
        diagram_element_id="conn-1",
        diagram_element_kind="connection",
        correspondence_kind_after="refines",
    )
    assert ref.diagram_element_kind == "connection"
    assert ref.correspondence_kind_after == "refines"


# ---------------------------------------------------------------------------
# diagram_entity_exists
# ---------------------------------------------------------------------------


def _fm_with_entities(entities: dict) -> dict:
    return {"diagram-entities": entities}


def test_entity_exists_found() -> None:
    fm = _fm_with_entities({"container": [{"id": "c1", "label": "Web"}, {"id": "c2"}]})
    assert diagram_entity_exists(fm, "c1") is True
    assert diagram_entity_exists(fm, "c2") is True


def test_entity_exists_not_found() -> None:
    fm = _fm_with_entities({"container": [{"id": "c1"}]})
    assert diagram_entity_exists(fm, "c99") is False


def test_entity_exists_empty_entities() -> None:
    assert diagram_entity_exists({}, "c1") is False
    assert diagram_entity_exists({"diagram-entities": {}}, "c1") is False
    assert diagram_entity_exists({"diagram-entities": {"container": []}}, "c1") is False


def test_entity_exists_multiple_types() -> None:
    fm = _fm_with_entities({
        "person": [{"id": "p1"}],
        "software-system": [{"id": "ss1"}],
        "container": [{"id": "cnt1"}],
    })
    assert diagram_entity_exists(fm, "p1") is True
    assert diagram_entity_exists(fm, "ss1") is True
    assert diagram_entity_exists(fm, "cnt1") is True
    assert diagram_entity_exists(fm, "x") is False


# ---------------------------------------------------------------------------
# diagram_connection_endpoints
# ---------------------------------------------------------------------------


def _fm_with_connections(conns: list) -> dict:
    return {"connections": conns}


def test_connection_endpoints_found() -> None:
    fm = _fm_with_connections([{"id": "dep-1", "source": "c1", "target": "c2", "type": "c4-uses"}])
    result = diagram_connection_endpoints(fm, "dep-1")
    assert result == ("c1", "c2")


def test_connection_endpoints_not_found() -> None:
    fm = _fm_with_connections([{"id": "dep-1", "source": "c1", "target": "c2"}])
    assert diagram_connection_endpoints(fm, "dep-99") is None


def test_connection_endpoints_no_connections_key() -> None:
    assert diagram_connection_endpoints({}, "dep-1") is None


def test_connection_endpoints_missing_source_or_target() -> None:
    fm = _fm_with_connections([{"id": "dep-1", "source": "c1"}])
    assert diagram_connection_endpoints(fm, "dep-1") is None

    fm2 = _fm_with_connections([{"id": "dep-1", "target": "c2"}])
    assert diagram_connection_endpoints(fm2, "dep-1") is None


# ---------------------------------------------------------------------------
# find_represents_entity
# ---------------------------------------------------------------------------


def _represents_binding(elem_id: str, entity_id: str, bid: str | None = None) -> Binding:
    return Binding(
        id=bid or f"bind-{elem_id}",
        subject=BindingSubject(kind="entity", id=elem_id),
        correspondence_kind="represents",
        target=Target(entity_id=entity_id),
    )


def _traces_binding(elem_id: str, entity_id: str) -> Binding:
    return Binding(
        id=f"trace-{elem_id}",
        subject=BindingSubject(kind="entity", id=elem_id),
        correspondence_kind="traces-to",
        target=Target(entity_id=entity_id),
    )


def test_find_represents_entity_found() -> None:
    b = _represents_binding("elem-1", "APP@abc.xyz.my-app")
    assert find_represents_entity([b], "elem-1") == "APP@abc.xyz.my-app"


def test_find_represents_entity_not_found() -> None:
    b = _traces_binding("elem-1", "APP@abc.xyz.my-app")
    assert find_represents_entity([b], "elem-1") is None


def test_find_represents_entity_wrong_element() -> None:
    b = _represents_binding("elem-2", "APP@abc.xyz.my-app")
    assert find_represents_entity([b], "elem-1") is None


def test_find_represents_entity_empty() -> None:
    assert find_represents_entity([], "elem-1") is None


# ---------------------------------------------------------------------------
# filter_bindings
# ---------------------------------------------------------------------------


def _refines_binding(elem_id: str, entity_id: str) -> Binding:
    return Binding(
        id=f"refine-{elem_id}",
        subject=BindingSubject(kind="entity", id=elem_id),
        correspondence_kind="refines",
        target=Target(entity_id=entity_id),
    )


def _abstracts_binding(elem_id: str, entity_id: str) -> Binding:
    return Binding(
        id=f"abs-{elem_id}",
        subject=BindingSubject(kind="entity", id=elem_id),
        correspondence_kind="abstracts",
        target=Target(entity_id=entity_id),
    )


def test_filter_removes_refines_and_abstracts() -> None:
    b_rep = _represents_binding("e1", "APP@1")
    b_ref = _refines_binding("e1", "APP@2")
    b_abs = _abstracts_binding("e1", "APP@3")
    b_trace = _traces_binding("e1", "APP@4")

    result = filter_bindings([b_rep, b_ref, b_abs, b_trace], "e1", "entity", frozenset({"refines", "abstracts"}))
    assert b_rep in result
    assert b_trace in result
    assert b_ref not in result
    assert b_abs not in result


def test_filter_preserves_other_elements() -> None:
    b1 = _refines_binding("e1", "APP@1")
    b2 = _refines_binding("e2", "APP@2")  # different element

    result = filter_bindings([b1, b2], "e1", "entity", frozenset({"refines"}))
    assert b1 not in result
    assert b2 in result  # kept because different element_id


def test_filter_empty_list() -> None:
    assert filter_bindings([], "e1", "entity", frozenset({"refines"})) == []


def test_filter_no_match_returns_all() -> None:
    b = _represents_binding("e1", "APP@1")
    result = filter_bindings([b], "e1", "entity", frozenset({"refines", "abstracts"}))
    assert result == [b]
