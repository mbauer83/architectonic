"""Unit tests for the generic preview service (preview.py).

Covers AC E: ViewProjector protocol dispatch, excluded-flag behavior,
scope-root handling, no C4 vocabulary in the service itself.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.derivation.preview import project_view_for_preview
from src.domain.viewpoints.view_derivations import DerivationSelection, SourceModelSnapshot, ViewDerivation
from src.domain.viewpoints.view_projection import ProjectedViewItem, ViewProjectionResult
from tests.application.derivation._fixtures import FakeQuery

_SNAP = SourceModelSnapshot(repo_scope="both", root_entity_id="ROOT")
_DERIVATION = ViewDerivation(
    id="__preview__",
    strategy="some-strategy",
    strategy_version=1,
    source_model_snapshot=_SNAP,
)


def _result(*items: ProjectedViewItem, selection: DerivationSelection | None = None) -> ViewProjectionResult:
    derivation = ViewDerivation(
        id="__preview__",
        strategy="some-strategy",
        strategy_version=1,
        source_model_snapshot=_SNAP,
        selection=selection,
    )
    return ViewProjectionResult(derivation=derivation, items=tuple(items))


def _item(entity_id: str, role: str = "external", display_class: str = "cls") -> ProjectedViewItem:
    return ProjectedViewItem(entity_id=entity_id, name=entity_id, display_class=display_class, role=role)


# ---------------------------------------------------------------------------
# Module without ViewProjector → None
# ---------------------------------------------------------------------------


def test_module_without_view_projector_returns_none() -> None:
    class NoProjector:
        pass

    query = FakeQuery([], [])
    assert project_view_for_preview(NoProjector(), "any", {}, query) is None


# ---------------------------------------------------------------------------
# Module returns None for standalone → None
# ---------------------------------------------------------------------------


class _StandaloneModule:
    def project_view(self, diagram_type: str, diagram_entities: Mapping[str, object], query: object) -> None:
        return None


def test_standalone_module_returns_none() -> None:
    query = FakeQuery([], [])
    assert project_view_for_preview(_StandaloneModule(), "any", {}, query) is None


# ---------------------------------------------------------------------------
# Excluded entity → present with excluded=True, not removed
# ---------------------------------------------------------------------------


class _FixedModule:
    def __init__(self, result: ViewProjectionResult) -> None:
        self._result = result

    def project_view(
        self, diagram_type: str, diagram_entities: Mapping[str, object], query: object
    ) -> ViewProjectionResult:
        return self._result


def test_excluded_entity_marked_excluded_not_removed() -> None:
    items = (_item("A"), _item("B"), _item("C"))
    sel = DerivationSelection(excluded_entity_ids=("B",))
    result = _result(*items, selection=sel)
    query = FakeQuery([], [])

    preview = project_view_for_preview(_FixedModule(result), "any", {}, query)

    assert preview is not None
    by_id = {i.entity_id: i for i in preview}
    assert "A" in by_id and "B" in by_id and "C" in by_id
    assert by_id["B"].excluded is True
    assert by_id["A"].excluded is False
    assert by_id["C"].excluded is False


def test_no_selection_no_excluded_flags() -> None:
    items = (_item("A"), _item("B"))
    result = _result(*items, selection=None)
    query = FakeQuery([], [])

    preview = project_view_for_preview(_FixedModule(result), "any", {}, query)

    assert preview is not None
    assert all(not i.excluded for i in preview)


# ---------------------------------------------------------------------------
# Scope root flagged role="scope"
# ---------------------------------------------------------------------------


def test_scope_root_has_role_scope() -> None:
    scope = _item("ROOT", role="scope", display_class="software-system")
    ext = _item("EXT", role="external")
    result = _result(scope, ext)
    query = FakeQuery([], [])

    preview = project_view_for_preview(_FixedModule(result), "any", {}, query)

    assert preview is not None
    root_item = next(i for i in preview if i.entity_id == "ROOT")
    assert root_item.role == "scope"


# ---------------------------------------------------------------------------
# Reads only DerivationSelection, not C4 keys
# ---------------------------------------------------------------------------


def test_preview_service_uses_derivation_selection_not_raw_entities() -> None:
    """Selection must come from result.derivation.selection, not diagram_entities._excluded_entity_ids."""
    scope = _item("ROOT", role="scope")
    ext = _item("EXT", role="external")
    # _excluded_entity_ids in diagram_entities should be IGNORED by the generic service
    diagram_entities = {"_excluded_entity_ids": ["EXT"]}
    # But derivation.selection has no exclusion → EXT should NOT be marked excluded
    result = _result(scope, ext, selection=None)
    query = FakeQuery([], [])

    preview = project_view_for_preview(_FixedModule(result), "any", diagram_entities, query)

    assert preview is not None
    ext_item = next(i for i in preview if i.entity_id == "EXT")
    assert ext_item.excluded is False
