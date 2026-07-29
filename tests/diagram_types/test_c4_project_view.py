"""Tests for _C4DiagramType.project_view (Seam C) and preview==render structural guarantee.

Covers AC D (project_view behavior, round-trip, standalone→None) and
AC F (preview==render: entity set from project_view_for_preview agrees with
what the engine projects for system-context, container, and component).
"""

from __future__ import annotations

from src.application.derivation.preview import project_view_for_preview
from src.diagram_types.c4._projection import MANIFEST, project_c4
from src.diagram_types.c4.component import module as c4_component
from src.diagram_types.c4.container import module as c4_container
from src.diagram_types.c4.system_context import module as c4_system_context
from src.domain.viewpoints.view_projection import ViewProjectionResult, ViewProjector
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_ROOT = "ROOT"
_PERSON_TYPES: frozenset[str] = frozenset({"business-actor", "role"})


def _make_query_with_child_and_neighbor():
    """Root → CHILD (composition), CHILD → EXT (serving)."""
    root = _entity(_ROOT, "application-component")
    child = _entity("CHILD", "application-component")
    ext = _entity("EXT", "application-component")
    struct = _connection("ROOT---CHILD@@archimate-composition", _ROOT, "CHILD", "archimate-composition")
    dep = _connection("CHILD---EXT@@archimate-serving", "CHILD", "EXT", "archimate-serving")
    return FakeQuery([root, child, ext], [struct, dep])


# ---------------------------------------------------------------------------
# ViewProjector protocol (AC C)
# ---------------------------------------------------------------------------


def test_c4_modules_implement_view_projector() -> None:
    for module in (c4_system_context, c4_container, c4_component):
        assert isinstance(module, ViewProjector), f"{module} should implement ViewProjector"


# ---------------------------------------------------------------------------
# AC D: standalone → None
# ---------------------------------------------------------------------------


def test_project_view_standalone_returns_none() -> None:
    query = FakeQuery([_entity(_ROOT)], [])
    result = c4_system_context.project_view("c4-system-context", {}, query)
    assert result is None


def test_project_view_empty_scope_id_returns_none() -> None:
    query = FakeQuery([_entity(_ROOT)], [])
    result = c4_container.project_view("c4-container", {"_scope_entity_id": ""}, query)
    assert result is None


# ---------------------------------------------------------------------------
# AC D: model-backed → ViewProjectionResult
# ---------------------------------------------------------------------------


def test_project_view_model_backed_returns_result() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)

    assert isinstance(result, ViewProjectionResult)


def test_project_view_derivation_strategy_and_version() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)

    assert result is not None
    assert result.derivation.strategy == "c4.scope-projection"
    assert result.derivation.strategy_version == 1


def test_project_view_derivation_repo_scope_both() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)

    assert result is not None
    assert result.derivation.source_model_snapshot.repo_scope == "both"


def test_project_view_derivation_params_mirror_engine_inputs() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)

    assert result is not None
    params = result.derivation.parameters
    assert params.get("diagram_type") == "c4-container"
    assert "internal_c4_type" in params
    assert "scope_entity_type" in params
    assert "person_archimate_types" in params


def test_project_view_items_carry_role_and_display_class() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)

    assert result is not None
    for item in result.items:
        assert item.role in ("scope", "internal", "external")
        assert item.display_class  # non-empty


def test_project_view_excluded_entity_ids_normalized_into_selection() -> None:
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT, "_excluded_entity_ids": ["EXT"]}

    result = c4_container.project_view("c4-container", de, query)

    assert result is not None
    sel = result.derivation.selection
    assert sel is not None
    assert "EXT" in sel.excluded_entity_ids


# ---------------------------------------------------------------------------
# AC D: Seam B / Seam C round-trip
# ---------------------------------------------------------------------------


def test_seam_b_and_seam_c_agree_on_entity_membership() -> None:
    """derivation.parameters → registered derive fn → CandidateSet.entity_ids
    should equal the non-scope items in project_view's items.
    """
    query = _make_query_with_child_and_neighbor()
    de = {"_scope_entity_id": _ROOT}

    result = c4_container.project_view("c4-container", de, query)
    assert result is not None

    # Seam B: re-run via manifest derive fn
    _, derive_fn = next(
        (spec, fn) for spec, fn in MANIFEST.strategies if spec.name == "c4.scope-projection"
    )
    assert derive_fn is not None
    candidate = derive_fn(
        dict(result.derivation.parameters),
        result.derivation.source_model_snapshot,
        query,
    )

    # Seam C: items from project_view
    seam_c_ids = {i.entity_id for i in result.items}

    # candidate_set excludes scope (for container); seam_c includes scope
    # → candidate_set.entity_ids == seam_c_ids - {scope entity}
    scope_id = result.derivation.source_model_snapshot.root_entity_id
    assert candidate.entity_ids == seam_c_ids - {scope_id}


# ---------------------------------------------------------------------------
# AC F: preview == render structural equivalence
# ---------------------------------------------------------------------------


def _preview_entity_ids(module: object, diagram_type: str, scope_id: str, query: FakeQuery) -> set[str]:
    de = {"_scope_entity_id": scope_id}
    items = project_view_for_preview(module, diagram_type, de, query)
    assert items is not None, f"Expected projection for {diagram_type}"
    return {i.entity_id for i in items}


def _engine_entity_ids(
    diagram_type: str, scope_id: str, query: FakeQuery, *, scope_entity_type: str, internal_c4_type: str
) -> set[str]:
    """Entity IDs that the engine projects (both seams agree: to_view_items)."""
    proj = project_c4(
        diagram_type, scope_id, query,
        internal_c4_type=internal_c4_type,
        scope_entity_type=scope_entity_type,
        person_archimate_types=_PERSON_TYPES,
    )
    return {i.entity_id for i in proj.to_view_items()}


def test_preview_equals_render_system_context() -> None:
    root = _entity(_ROOT, "application-component")
    ext = _entity("EXT", "application-component")
    conn = _connection("ROOT---EXT@@archimate-serving", _ROOT, "EXT", "archimate-serving")
    query = FakeQuery([root, ext], [conn])

    preview_ids = _preview_entity_ids(c4_system_context, "c4-system-context", _ROOT, query)
    engine_ids = _engine_entity_ids(
        "c4-system-context", _ROOT, query,
        scope_entity_type="software-system", internal_c4_type="container",
    )

    assert preview_ids == engine_ids


def test_preview_equals_render_container() -> None:
    query = _make_query_with_child_and_neighbor()

    preview_ids = _preview_entity_ids(c4_container, "c4-container", _ROOT, query)
    engine_ids = _engine_entity_ids(
        "c4-container", _ROOT, query,
        scope_entity_type="software-system", internal_c4_type="container",
    )

    assert preview_ids == engine_ids


def test_preview_equals_render_component() -> None:
    root = _entity(_ROOT, "application-component")
    fn = _entity("FN", "function")
    ext = _entity("EXT", "application-component")
    struct = _connection("ROOT---FN@@archimate-aggregation", _ROOT, "FN", "archimate-aggregation")
    dep = _connection("FN---EXT@@archimate-serving", "FN", "EXT", "archimate-serving")
    query = FakeQuery([root, fn, ext], [struct, dep])

    preview_ids = _preview_entity_ids(c4_component, "c4-component", _ROOT, query)
    engine_ids = _engine_entity_ids(
        "c4-component", _ROOT, query,
        scope_entity_type="container", internal_c4_type="component",
    )

    assert preview_ids == engine_ids
