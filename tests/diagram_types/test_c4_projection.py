"""Unit tests for the C4 projection engine (_c4_projection.py).

Covers AC A: three projection levels, role→item_type matrix, ModelQuery-only,
and AC B: strategy registration from the C4 module (not the generic package).
"""

from __future__ import annotations

from src.diagram_types.c4._projection import MANIFEST, _c4_item_type, project_c4
from src.domain.viewpoints.view_projection import ProjectedViewItem
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_ROOT = "ROOT"
_PERSON_TYPES: frozenset[str] = frozenset({"business-actor", "role"})
_COMMON = dict(
    scope_entity_type="software-system",
    internal_c4_type="container",
    person_archimate_types=_PERSON_TYPES,
)


# ---------------------------------------------------------------------------
# Registration checks (AC B)
# ---------------------------------------------------------------------------


def test_c4_projection_strategy_registered() -> None:
    specs = {spec.name: spec for spec, _ in MANIFEST.strategies}
    assert "c4.scope-projection" in specs
    assert specs["c4.scope-projection"].supported_filters == frozenset({"repo_scope"})


# ---------------------------------------------------------------------------
# _c4_item_type matrix (AC A)
# ---------------------------------------------------------------------------


def test_item_type_scope_returns_scope_entity_type() -> None:
    assert _c4_item_type("scope", "application-component", "software-system", "container", frozenset()) == (
        "software-system"
    )


def test_item_type_internal_app_component_container_level() -> None:
    assert _c4_item_type("internal", "application-component", "software-system", "container", frozenset()) == (
        "container"
    )


def test_item_type_internal_app_component_component_level() -> None:
    assert _c4_item_type("internal", "application-component", "software-system", "component", frozenset()) == (
        "component"
    )


def test_item_type_external_app_component_is_software_system() -> None:
    assert _c4_item_type("external", "application-component", "software-system", "container", frozenset()) == (
        "software-system"
    )


def test_item_type_external_business_actor_is_person() -> None:
    assert _c4_item_type("external", "business-actor", "software-system", "container", _PERSON_TYPES) == "person"


def test_item_type_external_role_is_person() -> None:
    assert _c4_item_type("external", "role", "software-system", "container", _PERSON_TYPES) == "person"


def test_item_type_external_unknown_type_is_software_system() -> None:
    assert _c4_item_type("external", "artifact", "software-system", "container", _PERSON_TYPES) == "software-system"


# ---------------------------------------------------------------------------
# c4-system-context (AC A)
# ---------------------------------------------------------------------------


def test_system_context_scope_item_has_role_scope() -> None:
    root = _entity(_ROOT, "application-component")
    query = FakeQuery([root], [])

    result = project_c4("c4-system-context", _ROOT, query, **_COMMON)

    scope_items = [i for i in result.items if i.role == "scope"]
    assert len(scope_items) == 1
    assert scope_items[0].entity_id == _ROOT
    assert scope_items[0].item_type == "software-system"


def test_system_context_no_structural_children_in_items() -> None:
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    result = project_c4("c4-system-context", _ROOT, query, **_COMMON)

    eids = {i.entity_id for i in result.items}
    assert "CHILD" not in eids


def test_system_context_neighbor_included_as_external() -> None:
    root = _entity(_ROOT, "application-component")
    ext = _entity("EXT", "application-component")
    conn = _connection("ROOT---EXT@@archimate-serving", _ROOT, "EXT", "archimate-serving")
    query = FakeQuery([root, ext], [conn])

    result = project_c4("c4-system-context", _ROOT, query, **_COMMON)

    ext_items = [i for i in result.items if i.entity_id == "EXT"]
    assert len(ext_items) == 1
    assert ext_items[0].role == "external"
    assert ext_items[0].item_type == "software-system"


def test_system_context_person_neighbor() -> None:
    root = _entity(_ROOT, "application-component")
    actor = _entity("ACTOR", "business-actor")
    conn = _connection("ACTOR---ROOT@@archimate-serving", "ACTOR", _ROOT, "archimate-serving")
    query = FakeQuery([root, actor], [conn])

    result = project_c4("c4-system-context", _ROOT, query, **_COMMON)

    person_items = [i for i in result.items if i.entity_id == "ACTOR"]
    assert len(person_items) == 1
    assert person_items[0].item_type == "person"


def test_system_context_candidate_set_includes_root() -> None:
    root = _entity(_ROOT, "application-component")
    query = FakeQuery([root], [])

    candidate = project_c4("c4-system-context", _ROOT, query, **_COMMON).to_candidate_set()

    assert _ROOT in candidate.entity_ids


def test_system_context_excludes_non_context_type_neighbor() -> None:
    root = _entity(_ROOT, "application-component")
    artifact = _entity("ART", "artifact")
    conn = _connection("ROOT---ART@@archimate-serving", _ROOT, "ART", "archimate-serving")
    query = FakeQuery([root, artifact], [conn])

    result = project_c4("c4-system-context", _ROOT, query, **_COMMON)

    assert "ART" not in {i.entity_id for i in result.items}


# ---------------------------------------------------------------------------
# c4-container (AC A)
# ---------------------------------------------------------------------------


def test_container_scope_item_present_with_role_scope() -> None:
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    result = project_c4("c4-container", _ROOT, query, **_COMMON)

    assert any(i.entity_id == _ROOT and i.role == "scope" for i in result.items)


def test_container_internal_child_item_type_is_internal_c4_type() -> None:
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    result = project_c4("c4-container", _ROOT, query, **_COMMON)

    internal = [i for i in result.items if i.entity_id == "CHILD"]
    assert len(internal) == 1
    assert internal[0].role == "internal"
    assert internal[0].item_type == "container"


def test_container_non_internal_type_child_excluded() -> None:
    """Children of types not in _CONTAINER_INTERNAL_TYPES are filtered out."""
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "artifact")  # not in _CONTAINER_INTERNAL_TYPES
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    result = project_c4("c4-container", _ROOT, query, **_COMMON)

    assert "CHILD" not in {i.entity_id for i in result.items if i.role == "internal"}


def test_container_candidate_set_excludes_root() -> None:
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    candidate = project_c4("c4-container", _ROOT, query, **_COMMON).to_candidate_set()

    assert _ROOT not in candidate.entity_ids
    assert "CHILD" in candidate.entity_ids


def test_container_external_neighbor_is_software_system() -> None:
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "service")
    ext = _entity("EXT", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    dep = _connection("CHILD---EXT@@archimate-serving", "CHILD", "EXT", "archimate-serving")
    query = FakeQuery([root, child, ext], [struct, dep])

    result = project_c4("c4-container", _ROOT, query, **_COMMON)

    ext_items = [i for i in result.items if i.entity_id == "EXT"]
    assert len(ext_items) == 1
    assert ext_items[0].role == "external"
    assert ext_items[0].item_type == "software-system"


# ---------------------------------------------------------------------------
# c4-component (AC A)
# ---------------------------------------------------------------------------


def test_component_internal_function_included() -> None:
    root = _entity(_ROOT, "application-component")
    fn = _entity("FN", "function")
    struct = _connection("ROOT---FN@@archimate-aggregation", _ROOT, "FN", "archimate-aggregation")
    query = FakeQuery([root, fn], [struct])

    result = project_c4("c4-component", _ROOT, query, **_COMMON)

    fn_items = [i for i in result.items if i.entity_id == "FN"]
    assert len(fn_items) == 1
    assert fn_items[0].role == "internal"
    assert fn_items[0].item_type == "container"  # internal_c4_type from _COMMON


def test_component_candidate_set_excludes_root() -> None:
    root = _entity(_ROOT, "application-component")
    fn = _entity("FN", "function")
    struct = _connection("ROOT---FN@@archimate-aggregation", _ROOT, "FN", "archimate-aggregation")
    query = FakeQuery([root, fn], [struct])

    candidate = project_c4("c4-component", _ROOT, query, **_COMMON).to_candidate_set()

    assert _ROOT not in candidate.entity_ids
    assert "FN" in candidate.entity_ids


def test_component_external_neighbor_is_software_system() -> None:
    root = _entity(_ROOT, "application-component")
    comp = _entity("COMP", "service")
    ext = _entity("EXT", "application-component")
    struct = _connection("ROOT---COMP@@archimate-composition", _ROOT, "COMP", "archimate-composition")
    dep = _connection("COMP---EXT@@archimate-serving", "COMP", "EXT", "archimate-serving")
    query = FakeQuery([root, comp, ext], [struct, dep])

    result = project_c4("c4-component", _ROOT, query, **_COMMON)

    ext_items = [i for i in result.items if i.entity_id == "EXT"]
    assert len(ext_items) == 1
    assert ext_items[0].item_type == "software-system"


# ---------------------------------------------------------------------------
# Unknown diagram_type
# ---------------------------------------------------------------------------


def test_unknown_diagram_type_returns_empty_projection() -> None:
    root = _entity(_ROOT, "application-component")
    query = FakeQuery([root], [])

    result = project_c4("c4-deployment", _ROOT, query, **_COMMON)

    assert result.items == ()
    assert result.connection_ids == ()
    assert result.to_candidate_set().entity_ids == frozenset()


# ---------------------------------------------------------------------------
# to_view_items (Seam C)
# ---------------------------------------------------------------------------


def test_to_view_items_contains_projected_view_items() -> None:
    root = _entity(_ROOT, "application-component")
    ext = _entity("EXT", "application-component")
    conn = _connection("ROOT---EXT@@archimate-serving", _ROOT, "EXT", "archimate-serving")
    query = FakeQuery([root, ext], [conn])

    items = project_c4("c4-system-context", _ROOT, query, **_COMMON).to_view_items()

    assert all(isinstance(i, ProjectedViewItem) for i in items)
    entity_ids = {i.entity_id for i in items}
    assert _ROOT in entity_ids
    assert "EXT" in entity_ids


def test_to_view_items_scope_has_role_scope() -> None:
    root = _entity(_ROOT, "application-component")
    query = FakeQuery([root], [])

    items = project_c4("c4-system-context", _ROOT, query, **_COMMON).to_view_items()

    scope = next(i for i in items if i.entity_id == _ROOT)
    assert scope.role == "scope"
    assert scope.display_class == "software-system"


# ---------------------------------------------------------------------------
# Seam B / Seam C round-trip (AC D prerequisite)
# ---------------------------------------------------------------------------


def test_candidate_set_entity_ids_subset_of_view_items() -> None:
    """For container: candidate_set entity_ids == {view_items minus scope}."""
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "service")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    query = FakeQuery([root, child], [struct])

    proj = project_c4("c4-container", _ROOT, query, **_COMMON)
    non_scope_ids = {i.entity_id for i in proj.to_view_items() if i.role != "scope"}
    candidate_ids = proj.to_candidate_set().entity_ids

    assert candidate_ids == non_scope_ids
