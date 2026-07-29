"""The datatype type's `editable_metadata` config is the single source of truth for which
classifier/attribute fields are user-editable descriptive metadata (vs structural). The PATCH
write-op whitelist and the frontend edit panels both derive from it — so these tests pin the
declaration and, crucially, guard it against drifting from the ontology schema."""

from __future__ import annotations

import src.infrastructure.app_bootstrap as app_bootstrap


def _classifier_ui_config():
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    dt = registry.all_diagram_types()["datatype"]
    return next(oe for oe in dt.ui_config.diagram_only_types if oe.entity_type == "classifier")


class TestEditableMetadataDeclaration:
    def test_entity_level_fields(self) -> None:
        spec = _classifier_ui_config().editable_metadata
        assert spec.field_names(None) == frozenset({"role", "provenance", "tags", "note"})

    def test_attribute_subpart_fields(self) -> None:
        spec = _classifier_ui_config().editable_metadata
        assert spec.field_names("attributes") == frozenset(
            {"role", "multiplicity", "optional", "default", "provenance", "note"}
        )

    def test_presentation_order_and_controls(self) -> None:
        spec = _classifier_ui_config().editable_metadata
        entity = [(f.field, f.control) for f in spec.fields_for(None)]
        assert entity[0] == ("role", "summary")  # summary first
        assert entity[-1] == ("note", "notes")  # note last
        controls = {f.field: f.control for f in spec.fields_for("attributes")}
        assert controls["optional"] == "boolean"
        assert controls["tags" if "tags" in controls else "role"]  # sanity

    def test_unknown_subpart_is_empty(self) -> None:
        assert _classifier_ui_config().editable_metadata.field_names("does-not-exist") == frozenset()


class TestEditableMetadataDoesNotDriftFromSchema:
    """A declared editable field MUST exist in the entity's ontology schema — the guard that keeps
    the single source honest (no editing a field the type doesn't define)."""

    def test_entity_fields_exist_in_classifier_schema(self) -> None:
        own = _classifier_ui_config()
        prop_names = {p.name for p in own.properties}
        for name in own.editable_metadata.field_names(None):
            assert name in prop_names, f"editable_metadata entity field {name!r} absent from classifier schema"

    def test_attribute_fields_exist_in_attribute_schema(self) -> None:
        own = _classifier_ui_config()
        attributes = next((p.schema for p in own.properties if p.name == "attributes"), {})
        items = attributes.get("items", {}) if isinstance(attributes, dict) else {}
        attr_props = items.get("properties", {}) if isinstance(items, dict) else {}
        for name in own.editable_metadata.field_names("attributes"):
            assert name in attr_props, f"editable_metadata attribute field {name!r} absent from attribute schema"
