from __future__ import annotations

from src.domain.guidance.guidance import GuidanceEntry, GuidanceKey, GuidanceOverlay
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, META_ONTOLOGY_ALIAS, load_archimate_4_module


class TestArchimate4LoaderGuidanceOverlay:
    def test_absent_guidance_param_matches_current_behavior(self) -> None:
        default = load_archimate_4_module(_PACKAGE_DIR)
        explicit_none = load_archimate_4_module(_PACKAGE_DIR, guidance=None)
        assert (
            default.entity_types["stakeholder"].create_when
            == explicit_none.entity_types["stakeholder"].create_when
        )

    def test_empty_overlay_matches_current_behavior(self) -> None:
        default = load_archimate_4_module(_PACKAGE_DIR)
        with_empty_overlay = load_archimate_4_module(_PACKAGE_DIR, guidance=GuidanceOverlay())
        assert (
            default.entity_types["stakeholder"].create_when
            == with_empty_overlay.entity_types["stakeholder"].create_when
        )

    def test_overlay_overrides_one_entity_types_guidance(self) -> None:
        baseline = load_archimate_4_module(_PACKAGE_DIR)
        assert baseline.entity_types["stakeholder"].create_when != "OVERRIDDEN"

        overlay = GuidanceOverlay(
            {
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS, concept_kind="entity", type_name="stakeholder"
                ): GuidanceEntry(create_when="OVERRIDDEN", never_create_when="OVERRIDDEN-NEVER"),
            }
        )
        overridden = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)

        assert overridden.entity_types["stakeholder"].create_when == "OVERRIDDEN"
        assert overridden.entity_types["stakeholder"].never_create_when == "OVERRIDDEN-NEVER"
        # unrelated entity types are untouched by the overlay
        assert (
            overridden.entity_types["capability"].create_when
            == baseline.entity_types["capability"].create_when
        )

    def test_overlay_overrides_one_connection_types_guidance(self) -> None:
        """A relationship type takes imported guidance the same way an element type does — the
        module ships the slots empty, so without this the connection guidance in a document would
        import and then serve nothing."""
        baseline = load_archimate_4_module(_PACKAGE_DIR)
        assert baseline.connection_types["archimate-serving"].create_when == ""

        overlay = GuidanceOverlay(
            {
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS, concept_kind="connection", type_name="archimate-serving"
                ): GuidanceEntry(create_when="SERVING-WHEN", never_create_when="SERVING-NEVER"),
            }
        )
        overridden = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)

        assert overridden.connection_types["archimate-serving"].create_when == "SERVING-WHEN"
        assert overridden.connection_types["archimate-serving"].never_create_when == "SERVING-NEVER"
        # An entity type of the same-named concept kind is a distinct key, so it stays empty.
        assert overridden.connection_types["archimate-flow"].create_when == ""

    def test_entity_and_connection_keys_do_not_cross_over(self) -> None:
        """``service`` is an entity type and ``archimate-serving`` a connection type; guidance keyed
        for one concept kind must never surface on the other."""
        overlay = GuidanceOverlay(
            {
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS, concept_kind="entity", type_name="service"
                ): GuidanceEntry(create_when="ENTITY-ONLY", never_create_when=""),
            }
        )
        module = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)
        assert module.entity_types["service"].create_when == "ENTITY-ONLY"
        assert all(info.create_when != "ENTITY-ONLY" for info in module.connection_types.values())
