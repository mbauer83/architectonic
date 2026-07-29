from __future__ import annotations

from src.domain.guidance.guidance import (
    GuidanceContextKey,
    GuidanceEntry,
    GuidanceKey,
    GuidanceOverlay,
    WorkspaceGuidance,
    guidance_overlay_from_mapping,
    workspace_guidance_from_mapping,
)


def _entry(text: str) -> GuidanceEntry:
    return GuidanceEntry(create_when=f"create: {text}", never_create_when=f"never: {text}")


class TestGuidanceOverlayLookup:
    def test_empty_overlay_is_noop(self) -> None:
        overlay = GuidanceOverlay()
        assert overlay.is_empty()
        key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        assert overlay.get(key) is None

    def test_known_key_resolves(self) -> None:
        key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        overlay = GuidanceOverlay({key: _entry("stakeholder")})
        assert not overlay.is_empty()
        assert overlay.get(key) == _entry("stakeholder")

    def test_unknown_key_passes_through_as_none(self) -> None:
        key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        other = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="capability")
        overlay = GuidanceOverlay({key: _entry("stakeholder")})
        assert overlay.get(other) is None


class TestGuidanceKeyShape:
    def test_entity_specialization_key(self) -> None:
        key = GuidanceKey(
            module_alias="archimate-4",
            concept_kind="entity",
            type_name="stakeholder",
            specialization="business-service",
        )
        overlay = GuidanceOverlay({key: _entry("business-service")})
        assert overlay.get(key) == _entry("business-service")
        base_key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        assert overlay.get(base_key) is None

    def test_connection_specialization_key(self) -> None:
        key = GuidanceKey(
            module_alias="archimate-4",
            concept_kind="connection",
            type_name="archimate-flow",
            specialization="money-flow",
        )
        overlay = GuidanceOverlay({key: _entry("money-flow")})
        assert overlay.get(key) == _entry("money-flow")

    def test_entity_and_connection_keys_are_distinct(self) -> None:
        entity_key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="service")
        connection_key = GuidanceKey(module_alias="archimate-4", concept_kind="connection", type_name="service")
        overlay = GuidanceOverlay({entity_key: _entry("entity-service")})
        assert overlay.get(entity_key) == _entry("entity-service")
        assert overlay.get(connection_key) is None


class TestGuidanceOverlayFromMapping:
    def test_entity_base_guidance(self) -> None:
        data = {
            "guidance_format": 4,
            "meta_ontologies": {
                "archimate-4": {
                    "motivation": {
                        "entity_types": {
                            "stakeholder": {"create_when": "c", "never_create_when": "n"},
                        },
                    },
                },
            },
        }
        overlay = guidance_overlay_from_mapping(data)
        key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        assert overlay.get(key) == GuidanceEntry(create_when="c", never_create_when="n")

    def test_entity_specialization_guidance(self) -> None:
        data = {
            "meta_ontologies": {
                "archimate-4": {
                    "motivation": {
                        "entity_types": {
                            "stakeholder": {
                                "create_when": "c",
                                "never_create_when": "n",
                                "specializations": {
                                    "business-service": {"create_when": "sc", "never_create_when": "sn"},
                                },
                            },
                        },
                    },
                },
            },
        }
        overlay = guidance_overlay_from_mapping(data)
        base_key = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="stakeholder")
        spec_key = GuidanceKey(
            module_alias="archimate-4",
            concept_kind="entity",
            type_name="stakeholder",
            specialization="business-service",
        )
        assert overlay.get(base_key) == GuidanceEntry(create_when="c", never_create_when="n")
        assert overlay.get(spec_key) == GuidanceEntry(create_when="sc", never_create_when="sn")

    def test_connection_specialization_without_base_guidance(self) -> None:
        """Reserved, not-yet-populated connection base guidance (D3) must not create an
        override entry that would blank out the module's own inline text."""
        data = {
            "meta_ontologies": {
                "archimate-4": {
                    "connection_types": {
                        "archimate-flow": {
                            "specializations": {
                                "money-flow": {"create_when": "mc", "never_create_when": "mn"},
                            },
                        },
                    },
                },
            },
        }
        overlay = guidance_overlay_from_mapping(data)
        base_key = GuidanceKey(module_alias="archimate-4", concept_kind="connection", type_name="archimate-flow")
        spec_key = GuidanceKey(
            module_alias="archimate-4",
            concept_kind="connection",
            type_name="archimate-flow",
            specialization="money-flow",
        )
        assert overlay.get(base_key) is None
        assert overlay.get(spec_key) == GuidanceEntry(create_when="mc", never_create_when="mn")

    def test_missing_meta_ontologies_key_returns_empty_overlay(self) -> None:
        assert guidance_overlay_from_mapping({}).is_empty()
        assert guidance_overlay_from_mapping({"meta_ontologies": "not-a-mapping"}).is_empty()

    def test_malformed_entries_are_skipped_not_raised(self) -> None:
        data = {
            "meta_ontologies": {
                "archimate-4": {
                    "motivation": {
                        "entity_types": {
                            "stakeholder": "not-a-mapping",
                            123: {"create_when": "ignored — non-string type name"},
                        },
                    },
                    "connection_types": "not-a-mapping",
                },
                "sysml-v2": "not-a-mapping",
            },
        }
        assert guidance_overlay_from_mapping(data).is_empty()

    def test_connection_guidance_at_the_root_node(self) -> None:
        """Relationship types are declared for the whole meta-ontology, so their slot sits on the
        alias itself — no domain in between."""
        data = {
            "meta_ontologies": {
                "archimate-4": {
                    "connection_types": {
                        "archimate-serving": {"create_when": "cw", "never_create_when": "nw"},
                    },
                },
            },
        }
        overlay = guidance_overlay_from_mapping(data)
        key = GuidanceKey(module_alias="archimate-4", concept_kind="connection", type_name="archimate-serving")
        assert overlay.get(key) == GuidanceEntry(create_when="cw", never_create_when="nw")


class TestGuidanceOverlayNestedContext:
    """Each node's ``context`` is keyed by the path that reaches it, because the document's nesting
    IS that path. The parser needs no hierarchy — placement validation is the import CLI's job, so
    the runtime cache is already clean."""

    def _doc(self) -> dict:
        return {
            "guidance_format": 4,
            "meta_ontologies": {
                "archimate-4": {
                    "context": "Naming and conceptualization across the whole model.",
                    "motivation": {
                        "context": "Why the architecture is shaped this way.",
                        "entity_types": {
                            "requirement": {"create_when": "cw", "never_create_when": "nw"},
                        },
                    },
                    "strategy": {"context": "The business model, org-independently."},
                },
            },
        }

    def test_root_context_is_keyed_by_the_alias_alone(self) -> None:
        overlay = guidance_overlay_from_mapping(self._doc())
        key = GuidanceContextKey("archimate-4", ("archimate-4",))
        assert overlay.context_for(key) == "Naming and conceptualization across the whole model."

    def test_node_context_is_keyed_by_its_full_path(self) -> None:
        overlay = guidance_overlay_from_mapping(self._doc())
        key = GuidanceContextKey("archimate-4", ("archimate-4", "motivation"))
        assert overlay.context_for(key) == "Why the architecture is shaped this way."

    def test_type_slots_parse_from_the_node_they_sit_under(self) -> None:
        overlay = guidance_overlay_from_mapping(self._doc())
        base = GuidanceKey(module_alias="archimate-4", concept_kind="entity", type_name="requirement")
        assert overlay.get(base) == GuidanceEntry(create_when="cw", never_create_when="nw")

    def test_node_without_context_field_produces_no_entry(self) -> None:
        doc = self._doc()
        doc["meta_ontologies"]["archimate-4"]["business"] = {"note": "no context key here"}
        overlay = guidance_overlay_from_mapping(doc)
        assert overlay.context_for(GuidanceContextKey("archimate-4", ("archimate-4", "business"))) is None

    def test_every_sibling_node_is_read(self) -> None:
        overlay = guidance_overlay_from_mapping(self._doc())
        key = GuidanceContextKey("archimate-4", ("archimate-4", "strategy"))
        assert overlay.context_for(key) is not None

    def test_paths_are_distinct_per_alias(self) -> None:
        doc = self._doc()
        doc["meta_ontologies"]["sysml-v2"] = {"context": "SysML framing."}
        overlay = guidance_overlay_from_mapping(doc)
        assert overlay.context_for(GuidanceContextKey("sysml-v2", ("sysml-v2",))) == "SysML framing."
        assert overlay.context_for(GuidanceContextKey("archimate-4", ("sysml-v2",))) is None


class TestWorkspaceGuidanceFromMapping:
    """The top-level ``workspace:`` section is one text for one level — no sub-nodes to key it by.
    A missing or unusable section is tolerated by omission."""

    def test_empty_when_section_absent(self) -> None:
        assert workspace_guidance_from_mapping({}).is_empty()
        assert WorkspaceGuidance().is_empty()

    def test_text_parsed(self) -> None:
        data = {"workspace": "Encode relations as connections, not in names or descriptions."}
        result = workspace_guidance_from_mapping(data)
        assert result.context == "Encode relations as connections, not in names or descriptions."
        assert not result.is_empty()

    def test_surrounding_whitespace_stripped(self) -> None:
        assert workspace_guidance_from_mapping({"workspace": "  text  \n"}).context == "text"

    def test_mapping_section_is_empty(self) -> None:
        """The earlier per-topic map shape carries no workspace text any more; it is ignored rather
        than half-read, and the operational upgrade is what folds it into one text."""
        data = {"workspace": {"a-topic": {"context": "text"}}}
        assert workspace_guidance_from_mapping(data).is_empty()

    def test_blank_and_non_string_sections_are_empty(self) -> None:
        assert workspace_guidance_from_mapping({"workspace": "   "}).is_empty()
        assert workspace_guidance_from_mapping({"workspace": 7}).is_empty()
