"""Renderer tests for the datatype diagram type (restricted UML class diagram).

Covers: classifier kinds, is_abstract, attribute compartment, optional marker,
identity / unique_keys key markers + composite key note, enumeration literals,
all five dt-* connection arrows, src/tgt multiplicity labels, generalization_set
constraint note, and collect_references binding extraction.
"""

from __future__ import annotations

from pathlib import Path

from src.diagram_types.datatype.renderer import DatatypePumlRenderer

_REPO = Path("/fake/root")


def _renderer() -> DatatypePumlRenderer:
    return DatatypePumlRenderer({})


def _render(*, classifiers=None, connections=None, generalization_sets=None) -> str:
    entities: dict[str, object] = {"classifier": classifiers or []}
    if generalization_sets is not None:
        entities["generalization_set"] = generalization_sets
    return _renderer().render_body(
        "Test Diagram",
        [],
        [],
        "datatype",
        _REPO,
        diagram_entities=entities,
        diagram_connections=connections or [],
    )


def _cls(cid, *, kind="class", label=None, **extra):
    d = {"id": cid, "classifier_kind": kind}
    if label:
        d["label"] = label
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# Classifier kinds
# ---------------------------------------------------------------------------


class TestClassifierKinds:
    def test_class_uses_class_keyword(self):
        out = _render(classifiers=[_cls("c1", label="Order")])
        assert 'class "Order"' in out

    def test_datatype_has_stereotype(self):
        out = _render(classifiers=[_cls("c1", kind="datatype", label="Money")])
        assert "<<datatype>>" in out
        assert 'class "Money"' in out

    def test_stereotype_follows_alias(self):
        # PlantUML requires: class "Label" as Alias <<stereotype>>  (stereotype after alias)
        out = _render(classifiers=[_cls("c1", kind="datatype", label="Money")])
        assert 'class "Money" as _c1 <<datatype>> {' in out

    def test_enumeration_uses_enum_keyword(self):
        out = _render(classifiers=[_cls("c1", kind="enumeration", label="Status")])
        assert 'enum "Status"' in out

    def test_is_abstract_uses_abstract_class(self):
        out = _render(classifiers=[_cls("c1", label="Shape", is_abstract=True)])
        assert "abstract class" in out

    def test_variant_kind_is_no_longer_supported(self):
        # "variant" is no longer a classifier kind; rendering tolerates it as a plain class.
        out = _render(classifiers=[_cls("c1", kind="variant", label="Shape")])
        assert "<<variant>>" not in out

    def test_primitive_has_stereotype(self):
        out = _render(classifiers=[_cls("c1", kind="primitive", label="String")])
        assert "<<primitive>>" in out

    def test_alias_derived_from_id(self):
        out = _render(classifiers=[_cls("DOB@123.abc")])
        assert "as _DOB_123_abc" in out


# ---------------------------------------------------------------------------
# Attribute compartment + keys
# ---------------------------------------------------------------------------


class TestAttributes:
    def test_attribute_name_present(self):
        out = _render(classifiers=[_cls("c1", attributes=[{"id": "a1", "name": "price", "type": "decimal"}])])
        assert "price" in out
        assert "decimal" in out

    def test_attribute_multiplicity_present(self):
        out = _render(classifiers=[_cls("c1", attributes=[{
            "id": "a1", "name": "tags", "type": "string", "multiplicity": "0..*"
        }])])
        assert "[0..*]" in out

    def test_optional_marker(self):
        out = _render(classifiers=[_cls("c1", attributes=[{
            "id": "a1", "name": "nickname", "type": "string", "optional": True
        }])])
        assert "{optional}" in out

    def test_identity_marks_member_attribute(self):
        out = _render(classifiers=[_cls(
            "c1",
            attributes=[{"id": "a1", "name": "id", "type": "uuid"}],
            identity=["a1"],
        )])
        assert "{id}" in out

    def test_no_identity_no_id_marker(self):
        out = _render(classifiers=[_cls("c1", attributes=[{"id": "a1", "name": "name", "type": "string"}])])
        assert "{id}" not in out

    def test_named_unique_key_marker(self):
        out = _render(classifiers=[_cls(
            "c1",
            attributes=[{"id": "a1", "name": "email", "type": "string"}],
            unique_keys=[{"name": "email", "attribute_ids": ["a1"]}],
        )])
        assert "{unique:email}" in out

    def test_unnamed_unique_key_marker(self):
        out = _render(classifiers=[_cls(
            "c1",
            attributes=[{"id": "a1", "name": "email", "type": "string"}],
            unique_keys=[{"attribute_ids": ["a1"]}],
        )])
        assert "{unique}" in out

    def test_composite_key_note_uses_names(self):
        out = _render(classifiers=[_cls(
            "c1",
            attributes=[{"id": "a1", "name": "tenant"}, {"id": "a2", "name": "number"}],
            unique_keys=[{"name": "tn", "attribute_ids": ["a1", "a2"]}],
        )])
        assert "«unique tn» (tenant, number)" in out

    def test_no_legacy_unique_constraints_note(self):
        out = _render(classifiers=[_cls(
            "c1",
            attributes=[{"id": "a1", "name": "tenant"}, {"id": "a2", "name": "number"}],
            unique_keys=[{"attribute_ids": ["a1", "a2"]}],
        )])
        assert "{unique(" not in out


# ---------------------------------------------------------------------------
# Enumeration literals
# ---------------------------------------------------------------------------


class TestLiterals:
    def test_literals_in_body(self):
        out = _render(classifiers=[_cls(
            "c1", kind="enumeration", label="Color",
            literals=["RED", "GREEN", "BLUE"],
        )])
        assert "RED" in out
        assert "GREEN" in out
        assert "BLUE" in out

    def test_literals_not_rendered_for_class_kind(self):
        out = _render(classifiers=[_cls("c1", kind="class", literals=["GHOST"])])
        assert "GHOST" not in out


# ---------------------------------------------------------------------------
# dt-* connection arrows
# ---------------------------------------------------------------------------


class TestConnectionArrows:
    def _conn(self, conn_type):
        return {"id": "e1", "source": "a", "target": "b", "conn_type": conn_type}

    def test_dt_association_arrow(self):
        assert " -- " in _render(connections=[self._conn("dt-association")])

    def test_dt_aggregation_arrow(self):
        assert "o--" in _render(connections=[self._conn("dt-aggregation")])

    def test_dt_composition_arrow(self):
        assert "*--" in _render(connections=[self._conn("dt-composition")])

    def test_dt_generalization_arrow(self):
        assert "--|>" in _render(connections=[self._conn("dt-generalization")])

    def test_dt_dependency_arrow(self):
        assert "..>" in _render(connections=[self._conn("dt-dependency")])

    def test_unknown_conn_type_excluded(self):
        out = _render(connections=[{"id": "e1", "source": "a", "target": "b", "conn_type": "seq-from"}])
        assert "seq-from" not in out


# ---------------------------------------------------------------------------
# Multiplicity labels
# ---------------------------------------------------------------------------


class TestMultiplicity:
    def test_tgt_multiplicity_in_output(self):
        out = _render(connections=[{
            "id": "e1", "source": "a", "target": "b",
            "conn_type": "dt-association", "tgt_multiplicity": "0..*",
        }])
        assert '"0..*"' in out

    def test_src_multiplicity_in_output(self):
        out = _render(connections=[{
            "id": "e1", "source": "a", "target": "b",
            "conn_type": "dt-association", "src_multiplicity": "1",
        }])
        assert '"1"' in out

    def test_connection_label_in_output(self):
        out = _render(connections=[{
            "id": "e1", "source": "a", "target": "b",
            "conn_type": "dt-association", "label": "owns",
        }])
        assert ": owns" in out


class TestNotes:
    def test_classifier_note_in_output(self):
        out = _render(classifiers=[_cls("c1", label="Order", note="Aggregate root")])
        assert "note right of _c1" in out
        assert "Aggregate root" in out

    def test_connection_note_in_output(self):
        out = _render(connections=[{
            "id": "e1", "source": "a", "target": "b",
            "conn_type": "dt-association", "note": "Derived relation",
        }])
        assert "note on link" in out
        assert "Derived relation" in out


# ---------------------------------------------------------------------------
# Generalization set
# ---------------------------------------------------------------------------


class TestGeneralizationSet:
    def _scene(self):
        classifiers = [
            _cls("g", label="PaymentMethod", is_abstract=True),
            _cls("card", label="Card"),
            _cls("pp", label="PayPal"),
        ]
        connections = [
            {"id": "e1", "conn_type": "dt-generalization", "source": "card", "target": "g",
             "generalization_set": "GS@1.x.m"},
            {"id": "e2", "conn_type": "dt-generalization", "source": "pp", "target": "g",
             "generalization_set": "GS@1.x.m"},
        ]
        sets = [{"id": "GS@1.x.m", "label": "method", "is_covering": True, "is_disjoint": True}]
        return classifiers, connections, sets

    def test_constraint_note_rendered_on_general_end(self):
        classifiers, connections, sets = self._scene()
        out = _render(classifiers=classifiers, connections=connections, generalization_sets=sets)
        assert "note bottom of _g" in out
        assert "GeneralizationSet «method» {complete, disjoint}" in out

    def test_set_note_appended_to_constraint_note(self):
        classifiers, connections, sets = self._scene()
        sets = [{**sets[0], "note": "Cases are mutually exclusive by regulation."}]
        out = _render(classifiers=classifiers, connections=connections, generalization_sets=sets)
        assert "GeneralizationSet «method» {complete, disjoint}" in out
        assert "Cases are mutually exclusive by regulation." in out

    def test_incomplete_overlapping_constraint(self):
        classifiers, connections, _ = self._scene()
        sets = [{"id": "GS@1.x.m", "label": "method", "is_covering": False, "is_disjoint": False}]
        out = _render(classifiers=classifiers, connections=connections, generalization_sets=sets)
        assert "{incomplete, overlapping}" in out

    def test_unreferenced_set_renders_no_note(self):
        out = _render(
            classifiers=[_cls("g", label="X")],
            generalization_sets=[{"id": "GS@1.x.m", "label": "m", "is_covering": True}],
        )
        assert "GeneralizationSet" not in out


# ---------------------------------------------------------------------------
# collect_references
# ---------------------------------------------------------------------------


class TestCollectReferences:
    def _bindings(self, entity_ids=(), conn_ids=()):
        result = []
        for eid in entity_ids:
            result.append({"id": f"b_{eid}", "target": {"entity_id": eid}})
        for cid in conn_ids:
            result.append({"id": f"b_{cid}", "target": {"connection_id": cid}})
        return result

    def test_entity_ids_extracted_from_bindings(self):
        refs = _renderer().collect_references(
            "datatype", _REPO,
            bindings=self._bindings(entity_ids=["DOB@1.abc", "DOB@2.def"]),
        )
        assert "DOB@1.abc" in refs.entity_ids
        assert "DOB@2.def" in refs.entity_ids

    def test_connection_ids_extracted_from_bindings(self):
        refs = _renderer().collect_references(
            "datatype", _REPO,
            bindings=self._bindings(conn_ids=["DOB@1---DOB@2@@archimate-association"]),
        )
        assert "DOB@1---DOB@2@@archimate-association" in refs.connection_ids

    def test_empty_bindings_returns_empty_refs(self):
        refs = _renderer().collect_references("datatype", _REPO, bindings=[])
        assert refs.entity_ids == ()
        assert refs.connection_ids == ()

    def test_no_duplicates_in_entity_ids(self):
        bindings = self._bindings(entity_ids=["DOB@1.abc"]) * 2
        refs = _renderer().collect_references("datatype", _REPO, bindings=bindings)
        assert refs.entity_ids.count("DOB@1.abc") == 1
