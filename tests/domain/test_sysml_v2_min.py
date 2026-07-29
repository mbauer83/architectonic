"""Tests for the sysml_v2_min ontology module."""

from __future__ import annotations

import pytest

from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.sysml_v2_min import module

# ── Basic structure ───────────────────────────────────────────────────────────


def test_module_satisfies_protocol() -> None:
    assert isinstance(module, OntologyModule)


def test_module_name() -> None:
    assert module.name == "sysml_v2_min"


def test_display_section_id() -> None:
    assert module.display_section_id == "sysml"


# ── Entity types ──────────────────────────────────────────────────────────────


EXPECTED_ENTITY_TYPES = [
    "part-definition",
    "part-usage",
    "action-definition",
    "action-usage",
    "port-definition",
    "port-usage",
    "item-definition",
    "item-usage",
    "requirement-definition",
    "requirement-usage",
]


def test_all_ten_entity_types_present() -> None:
    names = set(module.entity_types.keys())
    for expected in EXPECTED_ENTITY_TYPES:
        assert EntityTypeName(expected) in names, f"Missing entity type: {expected}"


def test_entity_type_count() -> None:
    assert len(module.entity_types) == 10


def test_prefixes() -> None:
    expected = {
        "part-definition": "PDF",
        "part-usage": "PU",
        "action-definition": "ADF",
        "action-usage": "AU",
        "port-definition": "PODF",
        "port-usage": "POU",
        "item-definition": "IDF",
        "item-usage": "IU",
        "requirement-definition": "RDF",
        "requirement-usage": "RU",
    }
    for etype, prefix in expected.items():
        assert module.entity_types[EntityTypeName(etype)].prefix == prefix


def test_hierarchy_domain_is_sysml() -> None:
    for etype, info in module.entity_types.items():
        assert info.hierarchy[0] == "sysml", f"{etype}: expected domain 'sysml', got {info.hierarchy[0]!r}"


def test_hierarchy_leaf_matches_type() -> None:
    for etype, info in module.entity_types.items():
        assert info.hierarchy[-1] == str(etype)


# ── Element classes ───────────────────────────────────────────────────────────


OWNED_CLASSES = ["definition", "usage", "interface", "requirement"]
BORROWED_CLASSES = ["structure-element", "behavior-element", "passive-structure-element"]


def test_owned_element_classes_declared() -> None:
    for cls in OWNED_CLASSES:
        assert cls in module.element_classes, f"Expected element class {cls!r} to be declared"


def test_borrowed_classes_not_redeclared() -> None:
    for cls in BORROWED_CLASSES:
        assert cls not in module.element_classes, (
            f"Class {cls!r} is declared in archimate_4 and must not be redeclared"
        )


# ── Class membership ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("etype,expected_cls", [
    ("part-definition", "definition"),
    ("part-usage", "usage"),
    ("action-definition", "definition"),
    ("action-usage", "usage"),
    ("port-definition", "definition"),
    ("port-usage", "usage"),
    ("item-definition", "definition"),
    ("item-usage", "usage"),
    ("requirement-definition", "definition"),
    ("requirement-usage", "usage"),
])
def test_definition_usage_class_membership(etype: str, expected_cls: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert expected_cls in info.classes


@pytest.mark.parametrize("etype", ["part-definition", "part-usage"])
def test_structure_element_class(etype: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert "structure-element" in info.classes


@pytest.mark.parametrize("etype", ["action-definition", "action-usage"])
def test_behavior_element_class(etype: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert "behavior-element" in info.classes


@pytest.mark.parametrize("etype", ["item-definition", "item-usage"])
def test_passive_structure_element_class(etype: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert "passive-structure-element" in info.classes


@pytest.mark.parametrize("etype", ["port-definition", "port-usage"])
def test_interface_class(etype: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert "interface" in info.classes


@pytest.mark.parametrize("etype", ["requirement-definition", "requirement-usage"])
def test_requirement_class(etype: str) -> None:
    info = module.entity_types[EntityTypeName(etype)]
    assert "requirement" in info.classes


def test_entity_types_with_class_definition() -> None:
    result = module.entity_types_with_class(ElementClassName("definition"))
    assert result == frozenset(
        EntityTypeName(t) for t in
        ["part-definition", "action-definition", "port-definition", "item-definition", "requirement-definition"]
    )


def test_entity_types_with_class_usage() -> None:
    result = module.entity_types_with_class(ElementClassName("usage"))
    assert result == frozenset(
        EntityTypeName(t) for t in
        ["part-usage", "action-usage", "port-usage", "item-usage", "requirement-usage"]
    )


# ── Connection types ──────────────────────────────────────────────────────────


EXPECTED_CONN_TYPES = [
    "feature-membership",
    "specialization",
    "feature-typing",
    "flow-connection",
    "allocation",
    "satisfy",
]


def test_all_six_connection_types_present() -> None:
    names = set(module.connection_types.keys())
    for ct in EXPECTED_CONN_TYPES:
        assert ConnectionTypeName(ct) in names, f"Missing connection type: {ct}"


def test_conn_lang_is_sysml() -> None:
    for ct, info in module.connection_types.items():
        assert info.conn_lang == "sysml", f"{ct}: expected conn_lang 'sysml', got {info.conn_lang!r}"


def test_feature_membership_classes() -> None:
    info = module.connection_types[ConnectionTypeName("feature-membership")]
    assert "containment" in info.classes
    assert "membership" in info.classes


def test_specialization_class() -> None:
    info = module.connection_types[ConnectionTypeName("specialization")]
    assert "specialization" in info.classes


def test_feature_typing_class() -> None:
    info = module.connection_types[ConnectionTypeName("feature-typing")]
    assert "typing" in info.classes


def test_flow_connection_class() -> None:
    info = module.connection_types[ConnectionTypeName("flow-connection")]
    assert "flow" in info.classes


def test_allocation_classes() -> None:
    info = module.connection_types[ConnectionTypeName("allocation")]
    assert "allocation" in info.classes
    assert "trace" in info.classes


def test_satisfy_classes() -> None:
    info = module.connection_types[ConnectionTypeName("satisfy")]
    assert "trace" in info.classes
    assert "satisfy" in info.classes


def test_connection_types_with_class_containment() -> None:
    result = module.connection_types_with_class("containment")
    assert ConnectionTypeName("feature-membership") in result


def test_connection_types_with_class_flow() -> None:
    result = module.connection_types_with_class("flow")
    assert ConnectionTypeName("flow-connection") in result


# ── Permitted relationships ───────────────────────────────────────────────────


def test_feature_membership_definition_to_usage() -> None:
    assert module.permits_connection(
        EntityTypeName("part-definition"),
        EntityTypeName("part-usage"),
        ConnectionTypeName("feature-membership"),
    )


def test_specialization_definition_to_definition() -> None:
    assert module.permits_connection(
        EntityTypeName("action-definition"),
        EntityTypeName("action-definition"),
        ConnectionTypeName("specialization"),
    )


def test_feature_typing_usage_to_definition() -> None:
    assert module.permits_connection(
        EntityTypeName("action-usage"),
        EntityTypeName("action-definition"),
        ConnectionTypeName("feature-typing"),
    )


def test_flow_connection_usage_to_usage() -> None:
    assert module.permits_connection(
        EntityTypeName("part-usage"),
        EntityTypeName("part-usage"),
        ConnectionTypeName("flow-connection"),
    )


def test_allocation_usage_to_usage() -> None:
    assert module.permits_connection(
        EntityTypeName("action-usage"),
        EntityTypeName("part-usage"),
        ConnectionTypeName("allocation"),
    )


def test_satisfy_requirement_usage_to_usage() -> None:
    assert module.permits_connection(
        EntityTypeName("requirement-usage"),
        EntityTypeName("action-usage"),
        ConnectionTypeName("satisfy"),
    )


def test_satisfy_requirement_usage_to_definition() -> None:
    assert module.permits_connection(
        EntityTypeName("requirement-usage"),
        EntityTypeName("part-definition"),
        ConnectionTypeName("satisfy"),
    )


def test_feature_membership_not_usage_to_definition() -> None:
    # feature-membership only goes definition → usage, not the reverse
    assert not module.permits_connection(
        EntityTypeName("part-usage"),
        EntityTypeName("part-definition"),
        ConnectionTypeName("feature-membership"),
    )


def test_specialization_not_usage_to_usage() -> None:
    assert not module.permits_connection(
        EntityTypeName("part-usage"),
        EntityTypeName("part-usage"),
        ConnectionTypeName("specialization"),
    )


def test_satisfy_not_from_part_usage() -> None:
    # only requirement-usage may be the source of satisfy
    assert not module.permits_connection(
        EntityTypeName("part-usage"),
        EntityTypeName("action-usage"),
        ConnectionTypeName("satisfy"),
    )


# ── Display section ───────────────────────────────────────────────────────────


def test_render_display_section() -> None:
    rendered = module.render_display_section("part-usage", "Wheel", "WH1")
    assert "label: Wheel" in rendered
    assert "alias: WH1" in rendered


def test_render_display_section_escapes_double_quotes() -> None:
    rendered = module.render_display_section("part-usage", 'Say "hello"', "X1")
    assert '"' not in rendered.split("label:")[1].split("\n")[0]


def test_extract_display_section_round_trip() -> None:
    rendered = module.render_display_section("part-usage", "Wheel", "WH1")
    parsed = module.extract_display_section(rendered)
    assert isinstance(parsed, dict)
    assert parsed.get("label") == "Wheel"
    assert parsed.get("alias") == "WH1"


def test_sprite_for_returns_none() -> None:
    assert module.sprite_for("part-usage") is None


# ── Registry integration ──────────────────────────────────────────────────────


def test_no_element_class_conflict_with_archimate() -> None:
    from src.infrastructure.app_bootstrap import build_module_registry
    registry = build_module_registry(complete_vocabulary=True)
    # all_element_classes raises ValueError on duplicate — if it succeeds, no conflict
    classes = registry.all_element_classes()
    for cls in OWNED_CLASSES:
        assert cls in classes


def test_entity_types_globally_unique() -> None:
    from src.infrastructure.app_bootstrap import build_module_registry
    registry = build_module_registry(complete_vocabulary=True)
    all_types = registry.all_entity_types()
    for etype in EXPECTED_ENTITY_TYPES:
        assert EntityTypeName(etype) in all_types


# ── Guidance overlay ──────────────────────────────────────────────────────────


class TestSysmlLoaderGuidanceOverlay:
    def test_absent_guidance_matches_current_behavior(self) -> None:
        from src.ontologies.sysml_v2_min._loader import _PACKAGE_DIR, load_sysml_module

        default = load_sysml_module(_PACKAGE_DIR)
        explicit_none = load_sysml_module(_PACKAGE_DIR, guidance=None)
        assert (
            default.entity_types["part-definition"].create_when
            == explicit_none.entity_types["part-definition"].create_when
        )

    def test_overlay_overrides_one_entity_types_guidance(self) -> None:
        from src.domain.guidance.guidance import GuidanceEntry, GuidanceKey, GuidanceOverlay
        from src.ontologies.sysml_v2_min._loader import _PACKAGE_DIR, META_ONTOLOGY_ALIAS, load_sysml_module

        overlay = GuidanceOverlay(
            {
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS, concept_kind="entity", type_name="part-definition"
                ): GuidanceEntry(create_when="OVERRIDDEN", never_create_when="OVERRIDDEN-NEVER"),
            }
        )
        overridden = load_sysml_module(_PACKAGE_DIR, guidance=overlay)

        assert overridden.entity_types["part-definition"].create_when == "OVERRIDDEN"
        assert overridden.entity_types["part-definition"].never_create_when == "OVERRIDDEN-NEVER"
