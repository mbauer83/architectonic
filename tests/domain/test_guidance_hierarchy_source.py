"""The standard guidance-hierarchy derivation over the real archimate-4 module (and the
override hook). The derived tree must be structurally sound (no validation errors), rooted at a
single ``meta_ontology`` node (the module alias), and place each entity type under its declared
domain with specializations qualified per type.
"""

from __future__ import annotations

from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel, GuidanceNode
from src.domain.guidance.guidance_hierarchy_source import (
    DOMAIN_LEVEL,
    ENTITY_TYPE_LEVEL,
    META_ONTOLOGY_LEVEL,
    SPECIALIZATION_LEVEL,
    derive_standard_hierarchy,
    resolve_guidance_hierarchy,
    specialization_node_id,
)

_ALIAS = "archimate-4"


def _archimate_module():
    from src.infrastructure.app_bootstrap import build_module_registry, resolve_meta_ontology_module

    module = resolve_meta_ontology_module("archimate-4", build_module_registry())
    assert module is not None
    return module


def _archimate_hierarchy() -> GuidanceHierarchy:
    return derive_standard_hierarchy(_archimate_module(), alias=_ALIAS)


class TestStandardDerivation:
    def test_derived_archimate_tree_is_sound(self) -> None:
        assert _archimate_hierarchy().validation_errors() == ()

    def test_levels_are_meta_domain_type_specialization(self) -> None:
        assert [level.id for level in _archimate_hierarchy().ordered_levels()] == [
            META_ONTOLOGY_LEVEL,
            DOMAIN_LEVEL,
            ENTITY_TYPE_LEVEL,
            SPECIALIZATION_LEVEL,
        ]

    def test_single_meta_ontology_root_is_the_alias(self) -> None:
        h = _archimate_hierarchy()
        meta_nodes = [n for n in h.nodes if n.level_id == META_ONTOLOGY_LEVEL]
        assert [n.node_id for n in meta_nodes] == [_ALIAS]
        assert meta_nodes[0].parent_node_id is None

    def test_domains_are_parented_to_the_meta_ontology_root(self) -> None:
        domain_nodes = [n for n in _archimate_hierarchy().nodes if n.level_id == DOMAIN_LEVEL]
        assert domain_nodes
        assert all(n.parent_node_id == _ALIAS for n in domain_nodes)

    def test_requirement_ancestry_is_meta_domain_type(self) -> None:
        chain = _archimate_hierarchy().ancestry(ENTITY_TYPE_LEVEL, "requirement")
        assert [(n.level_id, n.node_id) for n in chain] == [
            (META_ONTOLOGY_LEVEL, _ALIAS),
            (DOMAIN_LEVEL, "motivation"),
            (ENTITY_TYPE_LEVEL, "requirement"),
        ]

    def test_specialization_ancestry_is_meta_domain_type_spec(self) -> None:
        node = specialization_node_id("requirement", "constraint")
        chain = _archimate_hierarchy().ancestry(SPECIALIZATION_LEVEL, node)
        assert [(n.level_id, n.node_id) for n in chain] == [
            (META_ONTOLOGY_LEVEL, _ALIAS),
            (DOMAIN_LEVEL, "motivation"),
            (ENTITY_TYPE_LEVEL, "requirement"),
            (SPECIALIZATION_LEVEL, node),
        ]

    def test_domain_nodes_are_deduplicated(self) -> None:
        domain_ids = [n.node_id for n in _archimate_hierarchy().nodes if n.level_id == DOMAIN_LEVEL]
        assert len(domain_ids) == len(set(domain_ids))
        assert "motivation" in domain_ids


class TestOverrideHook:
    def test_module_provided_hierarchy_is_preferred(self) -> None:
        custom = GuidanceHierarchy(
            levels=(GuidanceLevel("concern_class", "Concern class", 0),),
            nodes=(GuidanceNode("concern_class", "safety"),),
        )

        class _Fake:
            def guidance_hierarchy(self) -> GuidanceHierarchy:
                return custom

        assert resolve_guidance_hierarchy(_Fake(), alias=_ALIAS) is custom  # type: ignore[arg-type]

    def test_falls_back_to_standard_when_absent(self) -> None:
        h = resolve_guidance_hierarchy(_archimate_module(), alias=_ALIAS)
        assert h.is_declared_level(META_ONTOLOGY_LEVEL)
        assert h.is_declared_level(DOMAIN_LEVEL)
