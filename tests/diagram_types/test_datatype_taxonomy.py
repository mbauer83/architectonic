"""Drift guard: every dt-* connection type must carry a relationship_kind that
is in the canonical RELATIONSHIP_KINDS set and must not be a visual class tag
(nesting / dynamic).  Fails CI on a typo or a missing RELATIONSHIP_KINDS entry.
"""

from __future__ import annotations

import src.infrastructure.app_bootstrap as app_bootstrap
from src.domain.ontology_representation.ontology_types import RELATIONSHIP_KINDS

_VISUAL_CLASS_TAGS = frozenset({"nesting", "dynamic"})

_DT_TYPES = frozenset({
    "dt-association",
    "dt-aggregation",
    "dt-composition",
    "dt-generalization",
    "dt-dependency",
})


def _dt_conn_types():
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    return registry.all_diagram_types()["datatype"].own_connection_types


def test_all_dt_types_present():
    names = frozenset(_dt_conn_types())
    assert _DT_TYPES <= names, f"Missing dt-* types: {_DT_TYPES - names}"


def test_every_dt_type_has_relationship_kind():
    missing = [
        name for name, info in _dt_conn_types().items()
        if name in _DT_TYPES and info.relationship_kind is None
    ]
    assert not missing, f"dt-* types with no relationship_kind: {missing}"


def test_every_dt_relationship_kind_in_allowed_set():
    bad = [
        (name, info.relationship_kind)
        for name, info in _dt_conn_types().items()
        if name in _DT_TYPES and info.relationship_kind not in RELATIONSHIP_KINDS
    ]
    assert not bad, (
        f"dt-* relationship_kind values not in RELATIONSHIP_KINDS {sorted(RELATIONSHIP_KINDS)}: {bad}"
    )


def test_no_dt_relationship_kind_is_visual_class():
    collisions = [
        (name, info.relationship_kind)
        for name, info in _dt_conn_types().items()
        if name in _DT_TYPES and info.relationship_kind in _VISUAL_CLASS_TAGS
    ]
    assert not collisions, (
        f"dt-* types whose relationship_kind collides with a visual class tag: {collisions}"
    )


# ── WU-0.2: classifier workspace identity ────────────────────────────────────

def _dt_classifier_entity_type():
    from src.domain.modules.module_types import EntityTypeName
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    return registry.all_diagram_types()["datatype"].diagram_entity_type_infos[EntityTypeName("classifier")]


def _dt_classifier_ui_config():
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    dt = registry.all_diagram_types()["datatype"]
    return next(oe for oe in dt.ui_config.diagram_only_types if oe.entity_type == "classifier")


def test_classifier_identity_scope_workspace():
    assert _dt_classifier_entity_type().identity_scope == "workspace"


def test_classifier_id_prefix_clf():
    assert _dt_classifier_entity_type().id_prefix == "CLF"


def test_classifier_ui_config_identity_scope():
    assert _dt_classifier_ui_config().identity_scope == "workspace"


def test_classifier_ui_config_id_prefix():
    assert _dt_classifier_ui_config().id_prefix == "CLF"
