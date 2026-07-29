"""Style-value vocabulary: semantic tokens and ``#rrggbb`` color literals are valid;
anything else is rejected at validation time instead of being silently painted neutral."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_presentation_validation import validate_presentation
from src.domain.viewpoints.viewpoint_style_values import is_hex_color, is_valid_style_value
from src.domain.viewpoints.viewpoints import PresentationSpec, RangeBand, StyleRule

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"score": "number"},
    connection_attribute_types={},
)


def _match_criteria() -> EntityCriteriaGroup:
    condition = AttributeCondition(
        attribute="type", comparator="eq", value=ValueRef(kind="literal", literal="application-component")
    )
    return EntityCriteriaGroup(children=(condition,))


class TestStyleValueVocabulary:
    def test_semantic_tokens_are_valid_for_color_and_notation_capabilities(self) -> None:
        for token in ("emphasis", "positive", "caution", "critical", "neutral"):
            assert is_valid_style_value("node_color", token)
            assert is_valid_style_value("node_shape", token)

    def test_scale_endpoint_tokens_are_valid_for_color_capabilities(self) -> None:
        for token in ("heat-near", "heat-far", "heat-low", "heat-high"):
            assert is_valid_style_value("node_color", token)

    def test_hex_colors_are_valid_for_color_capabilities_only(self) -> None:
        assert is_hex_color("#00ffAA")
        assert is_valid_style_value("edge_color", "#123abc")
        assert is_valid_style_value("cell_emphasis", "#123abc")
        assert not is_valid_style_value("node_shape", "#123abc")

    def test_garbage_is_invalid_for_color_capabilities(self) -> None:
        for value in ("", "blueish", "#12345", "#1234567", "rgb(1,2,3)", "#12 456"):
            assert not is_valid_style_value("node_color", value)

    def test_free_form_capabilities_accept_anything(self) -> None:
        assert is_valid_style_value("badges", "badge-warning")
        assert is_valid_style_value("badges", "anything at all")


class TestPresentationStyleValueValidation:
    def test_match_rule_with_hex_color_passes(self) -> None:
        rule = StyleRule(capability="node_color", match_criteria=_match_criteria(), value="#336699")
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert issues == []

    def test_match_rule_with_unknown_value_is_error(self) -> None:
        rule = StyleRule(capability="node_color", match_criteria=_match_criteria(), value="blueish")
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [("unknown-style-value", "/p/styling_rules/0/value")]

    def test_range_band_values_are_validated(self) -> None:
        rule = StyleRule(
            capability="node_color",
            mode="range",
            range_attribute="score",
            range_bands=(RangeBand(minimum=None, maximum=10, value="#00ff00"), RangeBand(10, None, "warmish")),
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [
            ("unknown-style-value", "/p/styling_rules/0/range_bands/1/value")
        ]

    def test_scale_tokens_are_validated(self) -> None:
        rule = StyleRule(
            capability="node_color", mode="scale", scale_attribute="score", scale_tokens=("cool", "#ff0000")
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [("unknown-style-value", "/p/styling_rules/0/scale_tokens/0")]

    def test_default_style_values_are_validated(self) -> None:
        presentation = PresentationSpec(representation="exploration", default_style={"node_color": "grayish"})
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [("unknown-style-value", "/p/default_style/node_color")]


class TestLayoutDisplayOption:
    def test_valid_layout_for_exploration_passes(self) -> None:
        presentation = PresentationSpec(representation="exploration", display_options={"layout": "radial"})
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert issues == []

    def test_unknown_layout_value_is_error(self) -> None:
        presentation = PresentationSpec(representation="exploration", display_options={"layout": "spiral"})
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [("unknown-layout", "/p/display_options/layout")]

    def test_layout_on_non_exploration_representation_is_error(self) -> None:
        presentation = PresentationSpec(representation="diagram", display_options={"layout": "radial"})
        issues = validate_presentation(presentation, path="/p", registries=_REGISTRIES, check_ergonomics=True)
        assert [(i.code, i.path) for i in issues] == [("unsupported-display-option", "/p/display_options/layout")]
