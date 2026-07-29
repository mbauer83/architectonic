"""Tests for WU-F1: primitive_types exposed via datatype diagram-type UI config."""

from __future__ import annotations

import src.infrastructure.app_bootstrap as app_bootstrap

_EXPECTED_PRIMITIVES = {"String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"}


def _datatype_ui_config():
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    return registry.find_diagram_type("datatype").ui_config


def test_datatype_ui_config_has_primitive_types():
    cfg = _datatype_ui_config()
    assert cfg.primitive_types, "datatype diagram type must declare primitive_types"


def test_datatype_primitive_types_contains_expected_scalars():
    cfg = _datatype_ui_config()
    missing = _EXPECTED_PRIMITIVES - set(cfg.primitive_types)
    assert not missing, f"Missing primitive types: {missing}"


def test_datatype_primitive_types_ordered_string_first():
    cfg = _datatype_ui_config()
    assert cfg.primitive_types[0] == "String", "String should be the first primitive type"


def test_other_diagram_type_has_empty_primitive_types():
    """Diagram types without a scalar catalog should return an empty tuple."""
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    activity_cfg = registry.find_diagram_type("activity").ui_config
    assert activity_cfg.primitive_types == (), "activity diagram type should have no primitive_types"
