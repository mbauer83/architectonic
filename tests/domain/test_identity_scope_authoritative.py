"""WU-0.1 guard: identity_scope and id_prefix are consistent across all catalog views.

The ontology is authoritative; UI config derives from it via _apply_ontology_fields.
Checks that both the diagram-entity EntityTypeInfo (from the ontology loader) and
DiagramOwnEntityTypeUiConfig (from the merged config) report identical values for classifier.
"""

from __future__ import annotations

import src.infrastructure.app_bootstrap as app_bootstrap
from src.diagram_types.datatype import module as datatype_module
from src.domain.modules.module_types import EntityTypeName


def _registry():
    return app_bootstrap.build_module_registry(complete_vocabulary=True)


def _datatype():
    return datatype_module  # the singleton loaded at import time


def test_classifier_identity_scope_in_entity_type_info():
    """EntityTypeInfo (ontology loader view) reports workspace + CLF."""
    et_info = _datatype().diagram_entity_type_infos[EntityTypeName("classifier")]
    assert et_info.identity_scope == "workspace"
    assert et_info.id_prefix == "CLF"


def test_classifier_identity_scope_in_ui_config():
    """DiagramOwnEntityTypeUiConfig (merged config view) reports workspace + CLF."""
    ui_entries = {oe.entity_type: oe for oe in _datatype().ui_config.diagram_only_types}
    clf_ui = ui_entries["classifier"]
    assert clf_ui.identity_scope == "workspace"
    assert clf_ui.id_prefix == "CLF"


def test_views_agree():
    """Both catalog views report the same identity_scope and id_prefix for every diagram entity."""
    dt = _datatype()
    ui_map = {oe.entity_type: oe for oe in dt.ui_config.diagram_only_types}
    for etype_name, et_info in dt.diagram_entity_type_infos.items():
        ui = ui_map.get(str(etype_name))
        if ui is None:
            continue
        assert ui.identity_scope == et_info.identity_scope, (
            f"{etype_name}: identity_scope mismatch ({ui.identity_scope!r} vs {et_info.identity_scope!r})"
        )
        assert ui.id_prefix == et_info.id_prefix, (
            f"{etype_name}: id_prefix mismatch ({ui.id_prefix!r} vs {et_info.id_prefix!r})"
        )


def test_absent_identity_scope_defaults_to_diagram(tmp_path):
    """An entity type that omits identity_scope defaults to 'diagram' (loader contract).

    Tested directly against the loader so it does not depend on the datatype module
    happening to declare a scope-less type (classifier and generalization_set are both
    workspace-scoped).
    """
    from src.domain.diagrams.diagram_ontology_loader import load_diagram_ontology

    ont = tmp_path / "ontology.yaml"
    ont.write_text(
        "entity_types:\n"
        "  widget:\n"
        "    classes: []\n"
        "    properties:\n"
        "      label: {type: string}\n",
        encoding="utf-8",
    )
    info = load_diagram_ontology(ont).entity_types[EntityTypeName("widget")]
    assert info.identity_scope == "diagram"
    assert info.id_prefix is None
