"""Navigation resolves from the shape the write path actually persists.

`test_c4_navigation.py` builds its fixtures with `entity_id` on the items and `_scope_entity_id` at
the top level. `strip_diagram_shorthand` removes **both** before a diagram is written, so those
fixtures describe a shape no persisted diagram has ever had — and the whole suite stayed green while
C4 element selection and drill-down were dead in the GUI.

So these fixtures are built the other way round: run a realistic authored payload through the *real*
normalization, assert the shorthand is gone, and only then ask navigation to resolve it. A fixture
that cannot drift from the write path is the point; asserting the strip first is what keeps it
honest if the persist rules change again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from src.application.modeling.binding_normalize import normalize_bindings, strip_diagram_shorthand
from src.diagram_types.c4._navigation import build_c4_navigation, resolve_scope_entity_id
from src.domain.diagrams.bindings import bindings_to_raw, element_entity_ids

_SYSTEM = "APP@1.aaaaaa.the-platform"
_CONTAINER = "APP@2.bbbbbb.the-api"


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str
    extra: dict[str, Any]


def _authored(scope_entity: str, *extra_items: tuple[str, str]) -> dict[str, Any]:
    """A payload as `artifact_create_diagram` receives it: shorthand `entity_id` on each item."""
    return {
        "system": [{"id": "platform", "label": "The Platform", "entity_id": scope_entity, "scope": True}],
        "container": [
            {"id": local_id, "label": local_id, "entity_id": entity_id}
            for local_id, entity_id in extra_items
        ],
    }


def _persist(authored: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, object]]]:
    """What reaches disk: bindings normalized out, shorthand stripped from the items."""
    bindings = bindings_to_raw(normalize_bindings(authored, None))
    stripped = strip_diagram_shorthand(authored) or {}
    return stripped, bindings


def test_the_write_path_really_does_strip_what_these_fixtures_assume() -> None:
    """The precondition. If this ever fails, every assertion below is testing a dead shape."""
    stripped, bindings = _persist(_authored(_SYSTEM))

    items = [item for value in stripped.values() if isinstance(value, list) for item in value]
    assert items, "the fixture should still carry items"
    assert all("entity_id" not in item for item in items), "entity_id must not survive persistence"
    assert "_scope_entity_id" not in stripped
    assert element_entity_ids(bindings) == {"platform": _SYSTEM}


def test_scope_resolves_from_the_persisted_bindings() -> None:
    stripped, bindings = _persist(_authored(_SYSTEM))

    assert resolve_scope_entity_id(stripped, bindings) == _SYSTEM


def test_drilldown_is_reachable_between_two_persisted_diagrams() -> None:
    """The symptom, end to end: L1 and L2 scoping the same system must see each other.

    Before the fix `scope_entity_id` returned `""` for both, `build_c4_navigation` produced empty
    parent/child lists, and `buildDrilldownByEntityId` therefore yielded `{}` — no badges.
    """
    stripped, bindings = _persist(_authored(_SYSTEM, ("api", _CONTAINER)))
    context = FakeDiagramRecord(
        artifact_id="CSC@1.aaaaaa.l1",
        diagram_type="c4-system-context",
        name="L1",
        extra={"diagram-entities": stripped, "bindings": bindings},
    )
    container = FakeDiagramRecord(
        artifact_id="CC@2.bbbbbb.l2",
        diagram_type="c4-container",
        name="L2",
        extra={"diagram-entities": stripped, "bindings": bindings},
    )
    repo = MagicMock()
    repo.list_diagrams = lambda: [context, container]
    repo.get_entity = lambda _eid: None

    navigation = build_c4_navigation(repo, context.artifact_id, "c4-system-context", stripped)

    assert navigation is not None
    assert [child["diagram_id"] for child in navigation["child_diagrams"]] == [container.artifact_id]


def test_a_landscape_is_the_level_above_a_system_context() -> None:
    """`_C4_LEVELS` once carried `c4-system-landscape` for a type nothing could create; the type
    exists now, and its level is 0 — above the system context rather than beside it."""
    repo = MagicMock()
    repo.list_diagrams = lambda: []
    repo.get_entity = lambda _eid: None

    navigation = build_c4_navigation(repo, "X@1.a.a", "c4-system-landscape", {})

    assert navigation is not None
    assert navigation["current_level"] == 0


def test_a_diagram_type_outside_the_c4_family_still_has_no_navigation() -> None:
    repo = MagicMock()
    repo.list_diagrams = lambda: []
    repo.get_entity = lambda _eid: None

    assert build_c4_navigation(repo, "X@1.a.a", "archimate", {}) is None
