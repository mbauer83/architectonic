"""Placement validation of a guidance document against the module it targets: the nesting must
match the module's declared hierarchy, which is what makes a misfiled entity type detectable
instead of silently served under the wrong framing."""

from __future__ import annotations

from src.domain.guidance.guidance_document import FilteredNode, filter_document
from src.domain.guidance.guidance_hierarchy_source import resolve_guidance_hierarchy
from src.infrastructure.app_bootstrap import build_module_registry, resolve_meta_ontology_module

_ALIAS = "archimate-4"


def _filtered(document: dict[str, object]) -> FilteredNode:
    registry = build_module_registry()
    module = resolve_meta_ontology_module(_ALIAS, registry)
    assert module is not None
    return filter_document(module, resolve_guidance_hierarchy(module, alias=_ALIAS), document, alias=_ALIAS)


class TestNodeNesting:
    def test_declared_domain_node_kept(self) -> None:
        result = _filtered({"motivation": {"context": "Why the architecture is shaped this way."}})
        assert result.matched == ["motivation.context"]
        assert result.content == {"motivation": {"context": "Why the architecture is shaped this way."}}

    def test_root_context_kept(self) -> None:
        result = _filtered({"context": "Naming across the whole model."})
        assert result.matched == ["context"]
        assert result.content == {"context": "Naming across the whole model."}

    def test_blank_context_reported(self) -> None:
        result = _filtered({"context": "   "})
        assert result.content == {}
        assert result.unmatched == ["context (context must be a non-empty string)"]

    def test_undeclared_node_reported(self) -> None:
        result = _filtered({"no-such-domain": {"context": "x"}})
        assert result.content == {}
        assert result.unmatched == ["no-such-domain (not a declared domain of 'archimate-4')"]

    def test_node_below_the_last_named_level_reported(self) -> None:
        """Entity types are named by a type slot, not by a nested node, so a node one level deeper
        than the domain has no level to be declared at."""
        result = _filtered({"motivation": {"goal": {"context": "x"}}})
        assert result.unmatched == ["motivation.goal (no guidance level below domain)"]

    def test_non_mapping_node_reported(self) -> None:
        result = _filtered({"motivation": "not-a-mapping"})
        assert result.unmatched == ["motivation (node must be a mapping)"]


class TestEntityTypePlacement:
    def test_type_under_its_own_domain_kept(self) -> None:
        result = _filtered({"motivation": {"entity_types": {"goal": {"create_when": "c"}}}})
        assert result.matched == ["motivation.entity_types.goal"]
        assert result.content["motivation"] == {"entity_types": {"goal": {"create_when": "c"}}}

    def test_type_under_another_domain_reported(self) -> None:
        """The document says the type is a strategy concept; the module says motivation. The
        disagreement is the finding."""
        result = _filtered({"strategy": {"entity_types": {"goal": {"create_when": "c"}}}})
        assert result.content == {}
        assert result.unmatched == ["strategy.entity_types.goal (declared under 'motivation', not 'strategy')"]

    def test_type_slot_at_the_root_reported(self) -> None:
        result = _filtered({"entity_types": {"goal": {"create_when": "c"}}})
        assert result.content == {}
        assert result.unmatched == ["entity_types (entity types belong under a domain node)"]

    def test_specialization_slug_validated_against_the_catalog(self) -> None:
        document = {
            "common": {
                "entity_types": {
                    "service": {
                        "specializations": {
                            "business-service": {"create_when": "known"},
                            "not-a-real-slug": {"create_when": "unknown"},
                        }
                    }
                }
            }
        }
        result = _filtered(document)
        assert "common.entity_types.service.specializations.business-service" in result.matched
        assert result.unmatched == ["common.entity_types.service.specializations.not-a-real-slug"]
        kept = result.content["common"]["entity_types"]["service"]["specializations"]  # type: ignore[index]
        assert list(kept) == ["business-service"]


class TestConnectionTypePlacement:
    def test_connection_types_at_the_root_kept(self) -> None:
        result = _filtered({"connection_types": {"archimate-serving": {"create_when": "c"}}})
        assert result.matched == ["connection_types.archimate-serving"]
        assert result.content == {"connection_types": {"archimate-serving": {"create_when": "c"}}}

    def test_connection_types_under_a_domain_reported(self) -> None:
        """A relationship type is declared for the whole meta-ontology, so filing it under one
        domain would claim a scope the ontology does not give it."""
        result = _filtered({"motivation": {"connection_types": {"archimate-influence": {"create_when": "c"}}}})
        assert result.content == {}
        assert result.unmatched == [
            "motivation.connection_types (connection types belong at the meta-ontology root)"
        ]

    def test_unknown_connection_type_reported(self) -> None:
        result = _filtered({"connection_types": {"archimate-not-real": {"create_when": "c"}}})
        assert result.unmatched == ["connection_types.archimate-not-real"]
