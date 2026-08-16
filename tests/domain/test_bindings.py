"""Tests for the Binding data model, schema, parsing, and shorthand normalization."""

from __future__ import annotations

import pytest

from src.domain.diagrams.bindings import (
    BINDING_SHORTHAND_SCHEMA,
    BINDINGS_ARRAY_SCHEMA,
    CORE_CORRESPONDENCE_KINDS,
    Binding,
    BindingSubject,
    ConnectionPathItem,
    DiagramLocalTarget,
    Target,
    binding_to_dict,
    bindings_to_raw,
    diagram_scope_entity_id,
    diagram_scope_entity_ids,
    parse_binding,
    parse_bindings,
    parse_target,
    scope_entity_ids,
)

# ---------------------------------------------------------------------------
# Target construction
# ---------------------------------------------------------------------------


class TestTargetTaggedUnion:
    def test_entity_id_target(self) -> None:
        t = Target(entity_id="APP@123.abc.Name")
        assert t.entity_id == "APP@123.abc.Name"
        assert t.connection_id is None

    def test_connection_id_target(self) -> None:
        t = Target(connection_id="A@1---B@2@@serving")
        assert t.connection_id == "A@1---B@2@@serving"

    def test_connection_ids_target(self) -> None:
        t = Target(connection_ids=("A@1---B@2@@serving", "B@2---C@3@@flow"))
        assert t.connection_ids == ("A@1---B@2@@serving", "B@2---C@3@@flow")

    def test_diagram_local_target(self) -> None:
        t = Target(diagram_local=DiagramLocalTarget(element_id="box-1"))
        assert t.diagram_local is not None
        assert t.diagram_local.element_id == "box-1"
        assert t.diagram_local.diagram_id is None

    def test_connection_path_target(self) -> None:
        path = (ConnectionPathItem(id="A---B@@serving"), ConnectionPathItem(id="B---C@@flow"))
        t = Target(connection_path=path)
        assert t.connection_path is not None
        assert len(t.connection_path) == 2

    def test_empty_target_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Target()

    def test_two_fields_set_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Target(entity_id="X@1.a.b", connection_id="A---B@@serving")


# ---------------------------------------------------------------------------
# parse_target
# ---------------------------------------------------------------------------


class TestParseTarget:
    def test_entity_id(self) -> None:
        t = parse_target({"entity_id": "APP@1.abc.Name"})
        assert t.entity_id == "APP@1.abc.Name"

    def test_connection_id(self) -> None:
        t = parse_target({"connection_id": "A@1---B@2@@serving"})
        assert t.connection_id == "A@1---B@2@@serving"

    def test_connection_ids(self) -> None:
        t = parse_target({"connection_ids": ["A@1---B@2@@serving"]})
        assert t.connection_ids == ("A@1---B@2@@serving",)

    def test_diagram_local_no_diagram_id(self) -> None:
        t = parse_target({"diagram_local": {"element_id": "box-1"}})
        assert t.diagram_local is not None
        assert t.diagram_local.element_id == "box-1"
        assert t.diagram_local.diagram_id is None

    def test_diagram_local_with_diagram_id(self) -> None:
        t = parse_target({"diagram_local": {"element_id": "box-1", "diagram_id": "DIAG@1"}})
        assert t.diagram_local is not None
        assert t.diagram_local.diagram_id == "DIAG@1"

    def test_connection_path(self) -> None:
        t = parse_target({"connection_path": [{"id": "A---B@@serving"}, {"id": "B---C@@flow", "reversed": True}]})
        assert t.connection_path is not None
        assert t.connection_path[1].reversed is True


# ---------------------------------------------------------------------------
# parse_binding / parse_bindings
# ---------------------------------------------------------------------------


class TestParseBinding:
    def _raw(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": "bind-1",
            "subject": {"kind": "entity", "id": "box-web"},
            "correspondence_kind": "represents",
            "target": {"entity_id": "APP@1.abc.Web"},
        }
        base.update(overrides)
        return base

    def test_basic_entity_binding(self) -> None:
        b = parse_binding(self._raw())
        assert b.id == "bind-1"
        assert b.subject.kind == "entity"
        assert b.subject.id == "box-web"
        assert b.correspondence_kind == "represents"
        assert b.target.entity_id == "APP@1.abc.Web"
        assert b.derived_from is None
        assert b.visual_role is None

    def test_diagram_subject_no_id(self) -> None:
        raw = self._raw(subject={"kind": "diagram"}, **{"id": "bind-scope"})
        b = parse_binding(raw)
        assert b.subject.kind == "diagram"
        assert b.subject.id is None

    def test_derived_from_and_visual_role(self) -> None:
        raw = self._raw(derived_from="derive-main", visual_role="primary")
        b = parse_binding(raw)
        assert b.derived_from == "derive-main"
        assert b.visual_role == "primary"

    def test_invalid_subject_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid binding subject kind"):
            parse_binding(self._raw(subject={"kind": "unknown", "id": "x"}))

    def test_subject_not_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a dict"):
            parse_binding(self._raw(subject="bad"))

    def test_target_not_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a dict"):
            parse_binding(self._raw(target="bad"))

    def test_parse_bindings_empty(self) -> None:
        assert parse_bindings(None) == []
        assert parse_bindings([]) == []

    def test_parse_bindings_skips_non_dicts(self) -> None:
        result = parse_bindings([self._raw(), "not-a-dict", None])  # type: ignore[list-item]
        assert len(result) == 1


# ---------------------------------------------------------------------------
# binding_to_dict / round-trip
# ---------------------------------------------------------------------------


class TestBindingRoundTrip:
    def _make(self, entity_id: str = "APP@1.a.X") -> Binding:
        return Binding(
            id="bind-1",
            subject=BindingSubject(kind="entity", id="box-web"),
            correspondence_kind="represents",
            target=Target(entity_id=entity_id),
        )

    def test_roundtrip_entity_id(self) -> None:
        b = self._make()
        d = binding_to_dict(b)
        b2 = parse_binding(d)
        assert b == b2

    def test_roundtrip_connection_ids(self) -> None:
        b = Binding(
            id="bind-2",
            subject=BindingSubject(kind="connection", id="edge-1"),
            correspondence_kind="abstracts",
            target=Target(connection_ids=("A@1---B@2@@serving",)),
        )
        d = binding_to_dict(b)
        assert d["target"] == {"connection_ids": ["A@1---B@2@@serving"]}
        b2 = parse_binding(d)
        assert b == b2

    def test_diagram_subject_no_id_in_dict(self) -> None:
        b = Binding(
            id="bind-scope",
            subject=BindingSubject(kind="diagram"),
            correspondence_kind="scoped-by",
            target=Target(entity_id="SYS@1.abc.Sys"),
        )
        d = binding_to_dict(b)
        assert "id" not in d["subject"]  # type: ignore[operator]

    def test_derived_from_included(self) -> None:
        b = Binding(
            id="bind-3",
            subject=BindingSubject(kind="entity", id="box-1"),
            correspondence_kind="represents",
            target=Target(entity_id="APP@1.x.Y"),
            derived_from="derive-main",
        )
        d = binding_to_dict(b)
        assert d["derived_from"] == "derive-main"

    def test_bindings_to_raw(self) -> None:
        bs = [self._make("APP@1.a.X"), self._make("APP@1.b.Y")]
        raw = bindings_to_raw(bs)
        assert isinstance(raw, list)
        assert len(raw) == 2


# ---------------------------------------------------------------------------
# Core kinds constant
# ---------------------------------------------------------------------------


class TestCoreCorrespondenceKinds:
    def test_contains_five_kinds(self) -> None:
        assert len(CORE_CORRESPONDENCE_KINDS) == 5

    def test_contains_all_expected(self) -> None:
        assert "represents" in CORE_CORRESPONDENCE_KINDS
        assert "abstracts" in CORE_CORRESPONDENCE_KINDS
        assert "refines" in CORE_CORRESPONDENCE_KINDS
        assert "scoped-by" in CORE_CORRESPONDENCE_KINDS
        assert "traces-to" in CORE_CORRESPONDENCE_KINDS


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


class TestBindingsArraySchema:
    def test_is_array_type(self) -> None:
        assert BINDINGS_ARRAY_SCHEMA["type"] == "array"

    def test_items_required_fields(self) -> None:
        items = BINDINGS_ARRAY_SCHEMA["items"]  # type: ignore[index]
        assert "id" in items["required"]  # type: ignore[index]
        assert "subject" in items["required"]  # type: ignore[index]
        assert "correspondence_kind" in items["required"]  # type: ignore[index]
        assert "target" in items["required"]  # type: ignore[index]

    def test_target_has_all_variant_properties(self) -> None:
        target_props = BINDINGS_ARRAY_SCHEMA["items"]["properties"]["target"]["properties"]  # type: ignore[index]
        assert "entity_id" in target_props
        assert "connection_id" in target_props
        assert "connection_ids" in target_props
        assert "diagram_local" in target_props
        assert "connection_path" in target_props


class TestBindingShorthandSchema:
    def test_target_is_required(self) -> None:
        assert "target" in BINDING_SHORTHAND_SCHEMA["required"]  # type: ignore[index]

    def test_no_connection_ids_in_shorthand(self) -> None:
        target_props = BINDING_SHORTHAND_SCHEMA["properties"]["target"]["properties"]  # type: ignore[index]
        assert "connection_ids" not in target_props
        assert "connection_path" not in target_props


# ---------------------------------------------------------------------------
# The set target, and the two readings of the scope it expresses
# ---------------------------------------------------------------------------


class TestEntityIdsTarget:
    """A diagram scoped by several entities at once — the C4 system landscape's binding shape."""

    def test_entity_ids_is_a_member_of_the_tagged_union(self) -> None:
        target = Target(entity_ids=("APP@1.a.X", "APP@2.b.Y"))
        assert target.entity_ids == ("APP@1.a.X", "APP@2.b.Y")
        assert target.entity_id is None

    def test_the_singular_and_the_set_are_still_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Target(entity_id="APP@1.a.X", entity_ids=("APP@2.b.Y",))

    def test_round_trip(self) -> None:
        binding = Binding(
            id="bind-scope",
            subject=BindingSubject(kind="diagram"),
            correspondence_kind="scoped-by",
            target=Target(entity_ids=("APP@1.a.X", "APP@2.b.Y")),
        )
        emitted = binding_to_dict(binding)

        assert emitted["target"] == {"entity_ids": ["APP@1.a.X", "APP@2.b.Y"]}
        assert parse_binding(emitted) == binding

    def test_the_array_schema_declares_it(self) -> None:
        properties = BINDINGS_ARRAY_SCHEMA["items"]["properties"]["target"]["properties"]  # type: ignore[index]
        assert properties["entity_ids"] == {"type": "array", "items": {"type": "string"}}


class TestScopeReadingsAgree:
    """The rule is stated over two representations, and they have to answer the same thing.

    The write path holds `Binding` records; the verifier and the read envelope hold unvalidated
    frontmatter dicts, where parsing first would raise on a file whose whole problem is that it is
    malformed. Three modules used to spell the loop themselves, and each read only the singular.
    """

    def _scoped_by(self, target: Target) -> Binding:
        return Binding(
            id="bind-scope",
            subject=BindingSubject(kind="diagram"),
            correspondence_kind="scoped-by",
            target=target,
        )

    @pytest.mark.parametrize(
        "target",
        [
            Target(entity_id="APP@1.a.X"),
            Target(entity_ids=("APP@1.a.X",)),
            Target(entity_ids=("APP@1.a.X", "APP@2.b.Y")),
        ],
    )
    def test_both_readings_answer_the_same_scope(self, target: Target) -> None:
        binding = self._scoped_by(target)

        assert scope_entity_ids([binding]) == diagram_scope_entity_ids([binding_to_dict(binding)])

    def test_both_readings_ignore_an_element_level_binding(self) -> None:
        element = Binding(
            id="bind-box",
            subject=BindingSubject(kind="entity", id="box-web"),
            correspondence_kind="represents",
            target=Target(entity_id="APP@1.a.X"),
        )

        assert scope_entity_ids([element]) == ()
        assert diagram_scope_entity_ids([binding_to_dict(element)]) == ()

    def test_the_singular_reader_is_a_filter_over_the_set_one(self) -> None:
        binding = self._scoped_by(Target(entity_ids=("APP@1.a.X", "APP@2.b.Y")))
        raw = [binding_to_dict(binding)]

        assert diagram_scope_entity_id(raw) == "APP@1.a.X"
        assert diagram_scope_entity_ids(raw) == ("APP@1.a.X", "APP@2.b.Y")
