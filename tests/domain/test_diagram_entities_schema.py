"""Tests for the meta-ontology schema generator (derive_diagram_entities_schema)."""

from __future__ import annotations

from src.domain.diagrams.diagram_entities_schema import derive_diagram_entities_schema
from src.domain.ontology_representation.ontology_protocol import (
    DiagramOwnEntityTypePropertySpec,
    DiagramOwnEntityTypeUiConfig,
)
from src.domain.ontology_representation.ontology_types import RequiredConnection


def _oe(
    entity_type: str,
    classes: tuple[str, ...] = (),
    properties: tuple[DiagramOwnEntityTypePropertySpec, ...] = (),
    min: int = 0,
) -> DiagramOwnEntityTypeUiConfig:
    return DiagramOwnEntityTypeUiConfig(
        entity_type=entity_type,
        label=entity_type.title(),
        plural=entity_type.title() + "s",
        classes=classes,
        min=min,
        properties=properties,
    )


class TestSchemaGeneratorBasic:
    def test_produces_array_per_entity_type(self) -> None:
        action = _oe("action", ("step",))
        schema = derive_diagram_entities_schema((action,))
        assert schema is not None
        assert "action" in schema["properties"]  # type: ignore[index]

    def test_array_key_is_entity_type_name(self) -> None:
        swimlane = _oe("swimlane", ("grouping",))
        schema = derive_diagram_entities_schema((swimlane,))
        assert schema is not None
        props = schema["properties"]  # type: ignore[index]
        assert "swimlane" in props
        assert "grouping" not in props  # element class is NOT the key

    def test_multiple_entity_types_each_get_own_array(self) -> None:
        swimlane = _oe("swimlane", ("grouping",))
        action = _oe("action", ("step",))
        decision = _oe("decision", ("step",))
        schema = derive_diagram_entities_schema((swimlane, action, decision))
        assert schema is not None
        props = schema["properties"]  # type: ignore[index]
        assert "swimlane" in props
        assert "action" in props
        assert "decision" in props

    def test_returns_none_for_empty_own_types(self) -> None:
        assert derive_diagram_entities_schema(()) is None

    def test_min_cardinality_propagates_to_array(self) -> None:
        swimlane = _oe("swimlane", ("grouping",), min=2)
        schema = derive_diagram_entities_schema((swimlane,))
        assert schema is not None
        assert schema["properties"]["swimlane"]["minItems"] == 2  # type: ignore[index]

    def test_no_minItems_when_min_is_zero(self) -> None:
        action = _oe("action", ("step",), min=0)
        schema = derive_diagram_entities_schema((action,))
        assert schema is not None
        assert "minItems" not in schema["properties"]["action"]  # type: ignore[index]


class TestSchemaGeneratorDefs:
    def test_each_entity_type_gets_defs_entry(self) -> None:
        action = _oe("action", ("step",))
        decision = _oe("decision", ("step",))
        schema = derive_diagram_entities_schema((action, decision))
        assert schema is not None
        defs = schema["$defs"]  # type: ignore[index]
        assert "action" in defs
        assert "decision" in defs

    def test_schema_has_id_required(self) -> None:
        swimlane = _oe("swimlane", ("grouping",))
        schema = derive_diagram_entities_schema((swimlane,))
        assert schema is not None
        swimlane_def = schema["$defs"]["swimlane"]  # type: ignore[index]
        assert "id" in swimlane_def["required"]  # type: ignore[index]

    def test_schema_includes_label_and_binding_properties(self) -> None:
        action = _oe("action", ("step",))
        schema = derive_diagram_entities_schema((action,))
        assert schema is not None
        action_def = schema["$defs"]["action"]  # type: ignore[index]
        assert "label" in action_def["properties"]  # type: ignore[index]
        assert "binding" in action_def["properties"]  # type: ignore[index]
        assert "entity_id" not in action_def["properties"]  # type: ignore[index]

    def test_domain_properties_included(self) -> None:
        props = (DiagramOwnEntityTypePropertySpec(name="lane_id", schema={"type": "string"}, required=False),)
        action = _oe("action", ("step",), properties=props)
        schema = derive_diagram_entities_schema((action,))
        assert schema is not None
        action_def = schema["$defs"]["action"]  # type: ignore[index]
        assert "lane_id" in action_def["properties"]  # type: ignore[index]

    def test_annotation_type_also_gets_own_array(self) -> None:
        note = DiagramOwnEntityTypeUiConfig(
            entity_type="note",
            label="Note",
            plural="Notes",
            classes=("annotation",),
            properties=(),
            required_connections=(
                RequiredConnection(
                    connection_type="step-note-of",
                    target="@step",
                    cardinality_min=1,
                    cardinality_max=1,
                ),
            ),
        )
        schema = derive_diagram_entities_schema((note,))
        assert schema is not None
        assert "note" in schema["properties"]  # type: ignore[index]


class TestActivityDiagramKindSchemaIntegration:
    def test_activity_kind_produces_valid_schema_from_ontology(self) -> None:
        from src.diagram_types.activity import module as activity

        guidance = activity.write_guidance()
        schema = guidance.diagram_entities_schema
        assert schema is not None
        props = schema["properties"]
        assert "swimlane" in props
        assert "action" in props
        assert "decision" in props
        assert "fork" in props
        assert "partition" in props
        assert "note" in props  # note is an entity type with its own array

    def test_activity_schema_no_element_class_keys(self) -> None:
        from src.diagram_types.activity import module as activity

        guidance = activity.write_guidance()
        schema = guidance.diagram_entities_schema
        assert schema is not None
        props = schema["properties"]
        # Element class names must NOT appear as array keys
        assert "step" not in props
        assert "grouping" not in props
        assert "annotation" not in props
        assert "control-flow" not in props

    def test_activity_schema_swimlane_has_min_2(self) -> None:
        from src.diagram_types.activity import module as activity

        guidance = activity.write_guidance()
        schema = guidance.diagram_entities_schema
        assert schema is not None
        assert schema["properties"]["swimlane"].get("minItems") == 2  # type: ignore[index]

    def test_activity_schema_note_has_text_and_side_properties(self) -> None:
        from src.diagram_types.activity import module as activity

        guidance = activity.write_guidance()
        schema = guidance.diagram_entities_schema
        assert schema is not None
        note_def = schema["$defs"]["note"]  # type: ignore[index]
        assert "text" in note_def["properties"]  # type: ignore[index]
        assert "side" in note_def["properties"]  # type: ignore[index]
        assert "text" in note_def["required"]  # type: ignore[index]
