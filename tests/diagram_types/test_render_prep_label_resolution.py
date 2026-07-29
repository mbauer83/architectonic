"""WU-1.6 acceptance: PreparedDatatypeDiagram render-prep + label resolution.

Acceptance criteria:
(a) Rename contract:
    - Define classifier 'Order' (CLF@1.ab.order) in diagram A.
    - Diagram B references CLF@1.ab.order; prepare_render_model → 'Order' in rendered PUML.
    - Rename label to 'Purchase' (same id); re-call prepare_render_model with updated candidate
      WITHOUT editing diagram B → 'Purchase' appears.

(b) Same-write contract:
    - diagram_entities defines classifier CLF@1.ab.x labeled 'NewClass' AND references it.
    - prepare_render_model resolves to 'NewClass' without a candidate (inline resolution).

Also:
- primitive type refs resolve to their name string
- dict type refs with an unresolved classifier id fall back to the id
- non-dict types (legacy strings) pass through unchanged
- prepare_render_model is called by _render_diagram_entities_puml
"""

from __future__ import annotations

from pathlib import Path

from src.diagram_types.datatype import module as datatype_module

# ---------------------------------------------------------------------------
# Stub candidate
# ---------------------------------------------------------------------------


class _StubEntity:
    def __init__(self, artifact_id: str, name: str) -> None:
        self.artifact_id = artifact_id
        self.name = name


class _StubCandidate:
    def __init__(self, entities: list[_StubEntity]) -> None:
        self._entities = entities

    def list_entities(self, *, artifact_type: str | None = None) -> list[_StubEntity]:
        return self._entities

    def list_diagrams(self, **_kwargs) -> list:
        return []

    def scope_for_path(self, path: Path) -> str:
        return "engagement"


def _candidate_with(*pairs: tuple[str, str]) -> _StubCandidate:
    return _StubCandidate([_StubEntity(id_, label) for id_, label in pairs])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _de_with_ref(
    ref_clf_id: str,
    referencing_clf_id: str = "CLF@2.cd.x",
    attr_name: str = "ref_field",
) -> dict:
    """diagram_entities that references an external classifier."""
    return {
        "classifier": [
            {
                "id": referencing_clf_id,
                "classifier_kind": "class",
                "attributes": [
                    {"name": attr_name, "type": {"kind": "classifier", "id": ref_clf_id}},
                ],
            }
        ]
    }


def _de_with_def_and_ref(
    clf_id: str = "CLF@1.ab.x",
    label: str = "NewClass",
) -> dict:
    """diagram_entities that DEFINES a classifier AND references it (same-write)."""
    return {
        "classifier": [
            {
                "id": clf_id,
                "label": label,
                "classifier_kind": "class",
                "attributes": [],
            },
            {
                "id": "CLF@2.cd.user",
                "label": "User",
                "classifier_kind": "class",
                "attributes": [
                    {"name": "ref", "type": {"kind": "classifier", "id": clf_id}},
                ],
            },
        ]
    }


def _render(prepared: dict) -> str:
    return datatype_module.renderer.render_body(
        "TestDiagram",
        [],
        [],
        "datatype",
        Path("."),
        diagram_entities=prepared,
        diagram_connections=[],
    )


# ---------------------------------------------------------------------------
# (a) Rename contract
# ---------------------------------------------------------------------------


def test_rename_contract_shows_initial_label() -> None:
    """Reference to CLF@1.ab.order renders as 'Order' when candidate has Order."""
    de = _de_with_ref("CLF@1.ab.order")
    candidate = _candidate_with(("CLF@1.ab.order", "Order"))
    prepared = datatype_module.prepare_render_model(de, candidate)
    puml = _render(prepared)
    assert "Order" in puml


def test_rename_contract_rerenders_with_new_label() -> None:
    """After rename (same id, new label 'Purchase'), re-preparing the same de shows 'Purchase'."""
    de = _de_with_ref("CLF@1.ab.order")
    candidate_after_rename = _candidate_with(("CLF@1.ab.order", "Purchase"))
    prepared = datatype_module.prepare_render_model(de, candidate_after_rename)
    puml = _render(prepared)
    assert "Purchase" in puml
    assert "CLF@1.ab.order" not in puml


# ---------------------------------------------------------------------------
# (b) Same-write contract
# ---------------------------------------------------------------------------


def test_same_write_contract_no_candidate_needed() -> None:
    """A classifier defined in diagram_entities resolves its own references inline."""
    de = _de_with_def_and_ref(clf_id="CLF@1.ab.x", label="NewClass")
    prepared = datatype_module.prepare_render_model(de)  # no candidate
    puml = _render(prepared)
    assert "NewClass" in puml
    assert "CLF@1.ab.x" not in puml


def test_same_write_contract_label_not_id_in_attr() -> None:
    """The attribute column shows the label, not the raw CLF@ id."""
    de = _de_with_def_and_ref(clf_id="CLF@9.zz.thing", label="Widget")
    prepared = datatype_module.prepare_render_model(de)
    puml = _render(prepared)
    assert "Widget" in puml


# ---------------------------------------------------------------------------
# Primitive type refs
# ---------------------------------------------------------------------------


def test_primitive_type_resolved_to_name() -> None:
    de = {
        "classifier": [
            {
                "id": "CLF@1.ab.x",
                "label": "MyClass",
                "classifier_kind": "class",
                "attributes": [
                    {"name": "label", "type": {"kind": "primitive", "name": "String"}},
                ],
            }
        ]
    }
    prepared = datatype_module.prepare_render_model(de)
    puml = _render(prepared)
    assert "String" in puml


# ---------------------------------------------------------------------------
# Fallback to id when classifier not found
# ---------------------------------------------------------------------------


def test_unresolved_classifier_falls_back_to_id() -> None:
    de = _de_with_ref("CLF@9.zz.missing")
    prepared = datatype_module.prepare_render_model(de)  # no candidate
    puml = _render(prepared)
    assert "CLF@9.zz.missing" in puml


# ---------------------------------------------------------------------------
# Legacy string type refs (pre-migration)
# ---------------------------------------------------------------------------


def test_legacy_string_type_passes_through() -> None:
    de = {
        "classifier": [
            {
                "id": "CLF@1.ab.x",
                "label": "MyClass",
                "classifier_kind": "class",
                "attributes": [
                    {"name": "old_field", "type": "String"},
                ],
            }
        ]
    }
    prepared = datatype_module.prepare_render_model(de)
    puml = _render(prepared)
    assert "String" in puml


# ---------------------------------------------------------------------------
# prepare_render_model called by _render_diagram_entities_puml
# ---------------------------------------------------------------------------


def test_render_entities_puml_calls_prepare() -> None:
    """_render_diagram_entities_puml routes through prepare_render_model for label resolution."""
    from src.infrastructure.write.artifact_write.diagram_render import (
        _render_diagram_entities_puml,
    )

    de = _de_with_def_and_ref(clf_id="CLF@3.ef.product", label="Product")
    puml = _render_diagram_entities_puml(
        "datatype", "Test", de, [], Path("."), candidate=None
    )
    assert "Product" in puml
    assert "CLF@3.ef.product" not in puml


def test_render_entities_puml_uses_candidate_for_external_label() -> None:
    """When a candidate is passed, external classifier labels are resolved."""
    from src.infrastructure.write.artifact_write.diagram_render import (
        _render_diagram_entities_puml,
    )

    de = _de_with_ref("CLF@1.ab.ext")
    candidate = _candidate_with(("CLF@1.ab.ext", "ExternalClass"))
    puml = _render_diagram_entities_puml(
        "datatype", "Test", de, [], Path("."), candidate=candidate
    )
    assert "ExternalClass" in puml
